import logging
import json
from typing import Dict, List, Optional, Union
import asyncio
import re
import io
from fastapi import HTTPException, status
import requests
from pyppeteer import launch
from PyPDF2 import PdfReader, PdfWriter

from app.config.settings import settings
from app.utils.constants import ErrorMessage
from app.schemas.resume import Resume
from app.services.storage import storage_service


logger = logging.getLogger(__name__)


class PrinterService:
    """
    Service for generating PDF and preview images of resumes.
    """
    async def get_browser(self):
        """
        Get a browser instance.
        """
        try:
            browser_url = f"{settings.CHROME_URL}?token={settings.CHROME_TOKEN}"
            
            browser = await launch(
                browserURL=browser_url,
                ignoreHTTPSErrors=settings.CHROME_IGNORE_HTTPS_ERRORS,
                headless=True
            )
            
            return browser
        except Exception as e:
            logger.error(f"Error connecting to browser: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=ErrorMessage.INVALID_BROWSER_CONNECTION
            )

    async def get_version(self) -> str:
        """
        Get browser version.
        """
        browser = await self.get_browser()
        version = await browser.version()
        await browser.close()
        return version

    async def print_resume(self, resume: Resume) -> str:
        """
        Generate a PDF for a resume.
        
        Args:
            resume: Resume object
            
        Returns:
            URL of the generated PDF
        """
        start_time = asyncio.get_event_loop().time()
        
        try:
            url = await self._generate_resume(resume)
            
            end_time = asyncio.get_event_loop().time()
            duration = int((end_time - start_time) * 1000)
            
            number_pages = len(resume.data.metadata.layout)
            logger.debug(f"Chrome took {duration}ms to print {number_pages} page(s)")
            
            return url
        except Exception as e:
            logger.error(f"Error printing resume: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=ErrorMessage.RESUME_PRINTER_ERROR
            )

    async def print_preview(self, resume: Resume) -> str:
        """
        Generate a preview image for a resume.
        
        Args:
            resume: Resume object
            
        Returns:
            URL of the generated preview image
        """
        start_time = asyncio.get_event_loop().time()
        
        try:
            url = await self._generate_preview(resume)
            
            end_time = asyncio.get_event_loop().time()
            duration = int((end_time - start_time) * 1000)
            
            logger.debug(f"Chrome took {duration}ms to generate preview")
            
            return url
        except Exception as e:
            logger.error(f"Error generating preview: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=ErrorMessage.RESUME_PRINTER_ERROR
            )

    async def _generate_resume(self, resume: Resume) -> str:
        """
        Generate a PDF for a resume.
        
        Args:
            resume: Resume object
            
        Returns:
            URL of the generated PDF
        """
        browser = await self.get_browser()
        page = await browser.newPage()
        
        public_url = str(settings.PUBLIC_URL)
        storage_url = str(settings.STORAGE_URL)
        
        url = public_url
        
        # In development, localhost needs to be translated to host.docker.internal for Docker networking
        if re.search(r'https?://localhost(:\d+)?', public_url) or re.search(r'https?://localhost(:\d+)?', storage_url):
            url = re.sub(r'localhost(:\d+)?', lambda m: f"host.docker.internal{m.group(1) or ''}", url)
            
            await page.setRequestInterception(True)
            
            # Intercept requests to fix localhost URLs
            async def intercept_request(request):
                if request.url.startswith(storage_url):
                    modified_url = re.sub(
                        r'localhost(:\d+)?', 
                        lambda m: f"host.docker.internal{m.group(1) or ''}", 
                        request.url
                    )
                    await request.continue_({"url": modified_url})
                else:
                    await request.continue_()
            
            page.on('request', intercept_request)
        
        # Convert resume data to JSON and set it in local storage
        resume_data_json = json.dumps(resume.data.dict())
        
        await page.evaluateOnNewDocument(
            f"""
            (data) => {{
                window.localStorage.setItem('resume', data);
            }}
            """,
            resume_data_json
        )
        
        # Navigate to the artboard preview
        await page.goto(f"{url}/artboard/preview", {"waitUntil": "networkidle0"})
        
        number_pages = len(resume.data.metadata.layout)
        pages_buffer = []
        
        # Process each page
        for page_index in range(1, number_pages + 1):
            # Get page element
            page_element = await page.querySelector(f'[data-page="{page_index}"]')
            
            if not page_element:
                logger.error(f"Page element {page_index} not found")
                continue
            
            # Get element dimensions
            width = await page.evaluate("(element) => element.scrollWidth", page_element)
            height = await page.evaluate("(element) => element.scrollHeight", page_element)
            
            # Cache the original HTML
            temporary_html = await page.evaluate(
                """
                (element) => {
                    const clonedElement = element.cloneNode(true);
                    const temporaryHtml = document.body.innerHTML;
                    document.body.innerHTML = clonedElement.outerHTML;
                    return temporaryHtml;
                }
                """,
                page_element
            )
            
            # Apply custom CSS if enabled
            css = resume.data.metadata.css
            
            if css.visible:
                await page.evaluate(
                    """
                    (cssValue) => {
                        const styleTag = document.createElement('style');
                        styleTag.textContent = cssValue;
                        document.head.append(styleTag);
                    }
                    """,
                    css.value
                )
            
            # Generate PDF for this page
            pdf_bytes = await page.pdf({
                "width": width,
                "height": height,
                "printBackground": True
            })
            
            pages_buffer.append(pdf_bytes)
            
            # Restore the original HTML
            await page.evaluate(
                """
                (temporaryHtml) => {
                    document.body.innerHTML = temporaryHtml;
                }
                """,
                temporary_html
            )
        
        # Close page and browser
        await page.close()
        await browser.close()
        
        # Merge PDFs using PyPDF2
        output_pdf = io.BytesIO()
        pdf_writer = PdfWriter()
        
        for page_bytes in pages_buffer:
            pdf_reader = PdfReader(io.BytesIO(page_bytes))
            pdf_writer.add_page(pdf_reader.pages[0])
        
        pdf_writer.write(output_pdf)
        output_pdf.seek(0)
        
        # Upload the PDF to storage
        url = storage_service.upload_object(
            user_id=resume.userId,
            type_="resumes",
            file_data=output_pdf.getvalue(),
            filename=resume.title
        )
        
        return url

    async def _generate_preview(self, resume: Resume) -> str:
        """
        Generate a preview image for a resume.
        
        Args:
            resume: Resume object
            
        Returns:
            URL of the generated preview image
        """
        browser = await self.get_browser()
        page = await browser.newPage()
        
        public_url = str(settings.PUBLIC_URL)
        storage_url = str(settings.STORAGE_URL)
        
        url = public_url
        
        # In development, localhost needs to be translated to host.docker.internal for Docker networking
        if re.search(r'https?://localhost(:\d+)?', public_url) or re.search(r'https?://localhost(:\d+)?', storage_url):
            url = re.sub(r'localhost(:\d+)?', lambda m: f"host.docker.internal{m.group(1) or ''}", url)
            
            await page.setRequestInterception(True)
            
            # Intercept requests to fix localhost URLs
            async def intercept_request(request):
                if request.url.startswith(storage_url):
                    modified_url = re.sub(
                        r'localhost(:\d+)?', 
                        lambda m: f"host.docker.internal{m.group(1) or ''}", 
                        request.url
                    )
                    await request.continue_({"url": modified_url})
                else:
                    await request.continue_()
            
            page.on('request', intercept_request)
        
        # Convert resume data to JSON and set it in local storage
        resume_data_json = json.dumps(resume.data.dict())
        
        await page.evaluateOnNewDocument(
            f"""
            (data) => {{
                window.localStorage.setItem('resume', data);
            }}
            """,
            resume_data_json
        )
        
        # Set viewport size to A4
        await page.setViewport({"width": 794, "height": 1123})
        
        # Navigate to the artboard preview
        await page.goto(f"{url}/artboard/preview", {"waitUntil": "networkidle0"})
        
        # Take a screenshot
        screenshot = await page.screenshot({"quality": 80, "type": "jpeg"})
        
        # Close page and browser
        await page.close()
        await browser.close()
        
        # Upload the screenshot to storage
        url = storage_service.upload_object(
            user_id=resume.userId,
            type_="previews",
            file_data=screenshot,
            filename=str(resume.id)
        )
        
        return url


# Singleton instance
printer_service = PrinterService()