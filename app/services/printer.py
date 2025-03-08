import logging
import json
import io
from typing import Dict, List, Optional, Union
import asyncio
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, ListFlowable, ListItem
from reportlab.pdfgen import canvas
from reportlab.platypus.flowables import Flowable
from fastapi import HTTPException, status
from PIL import Image

from app.config.settings import settings
from app.utils.constants import ErrorMessage
from app.schemas.resume import Resume
from app.services.storage import storage_service

logger = logging.getLogger(__name__)

class PrinterService:
    """
    Service for generating PDF and preview images of resumes using ReportLab.
    This maintains the same interface as the original implementation.
    """
    def __init__(self):
        """Initialize the service with template environment."""
        # Setup Jinja2 template environment for any HTML content rendering
        self.template_dir = Path(__file__).parent / "../templates"
        self.template_env = Environment(
            loader=FileSystemLoader(self.template_dir),
            autoescape=select_autoescape(['html', 'xml'])
        )
        
        # Create templates directory if it doesn't exist
        self.template_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize styles
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        """Setup custom paragraph styles for PDF generation"""
        # Heading styles
        self.styles.add(ParagraphStyle(
            name='ResumeHeading',
            parent=self.styles['Heading1'],
            fontSize=16,
            spaceAfter=6,
            alignment=1  # Center alignment
        ))
        
        # Section title style
        self.styles.add(ParagraphStyle(
            name='SectionTitle',
            parent=self.styles['Heading2'],
            fontSize=12,
            spaceAfter=6,
            borderWidth=1,
            borderColor=colors.black,
            borderPadding=2,
            borderRadius=None,
            endDots=None,
            splitLongWords=1,
            underlineWidth=0.5,
            underlineGap=1,
            underlineOffset=-2,
            underlineColor=colors.black,
        ))
        
        # Job title style
        self.styles.add(ParagraphStyle(
            name='JobTitle',
            parent=self.styles['Normal'],
            fontSize=10,
            fontName='Helvetica-Bold',
            spaceAfter=1
        ))
        
        # Normal text style
        self.styles.add(ParagraphStyle(
            name='ResumeNormal',
            parent=self.styles['Normal'],
            fontSize=10,
            spaceAfter=2
        ))
        
        # Contact info style
        self.styles.add(ParagraphStyle(
            name='ContactInfo',
            parent=self.styles['Normal'],
            fontSize=9,
            alignment=1  # Center alignment
        ))

    async def get_browser(self):
        """
        Stub for compatibility with original interface.
        """
        logger.warning("get_browser() called but ReportLab doesn't use a browser")
        return None

    async def get_version(self) -> str:
        """
        Get ReportLab version for compatibility with original interface.
        """
        import reportlab
        return f"ReportLab {reportlab.Version}"

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

            # Access dictionary with .get() method rather than attribute access
            number_pages = len(resume.data.get('metadata', {}).get('layout', []))
            logger.debug(f"ReportLab took {duration}ms to print {number_pages} page(s)")

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

            logger.debug(f"ReportLab took {duration}ms to generate preview")

            return url
        except Exception as e:
            logger.error(f"Error generating preview: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=ErrorMessage.RESUME_PRINTER_ERROR
            )

    def _get_page_size(self, layout):
        """Get page size for the given layout"""
        width = layout.get('width', 210)  # Default A4 width in mm
        height = layout.get('height', 297)  # Default A4 height in mm
        return (width * mm, height * mm)

    def _build_header(self, resume_data):
        """Build the header section with name and contact info"""
        elements = []
        
        # Name
        basics = resume_data.get('basics', {})
        name = basics.get('name', '')
        elements.append(Paragraph(name, self.styles['ResumeHeading']))
        elements.append(Spacer(1, 2 * mm))
        
        # Contact info
        contact_parts = []
        
        if 'email' in basics:
            contact_parts.append(basics['email'])
        
        if 'phone' in basics:
            contact_parts.append(basics['phone'])
        
        if 'location' in basics:
            location = basics['location']
            if 'city' in location and 'region' in location:
                contact_parts.append(f"{location['city']}, {location['region']}")
        
        if contact_parts:
            contact_info = " | ".join(contact_parts)
            elements.append(Paragraph(contact_info, self.styles['ContactInfo']))
            elements.append(Spacer(1, 6 * mm))
        
        return elements

    def _build_work_section(self, work_items):
        """Build work experience section"""
        elements = []
        
        for job in work_items:
            # Company and dates row
            job_header = f"<b>{job.get('position', '')}</b> - {job.get('company', '')}"
            date_range = f"{job.get('startDate', '')} - {job.get('endDate', 'Present')}"
            
            elements.append(
                Table(
                    [[Paragraph(job_header, self.styles['JobTitle']), 
                      Paragraph(date_range, self.styles['ResumeNormal'])]],
                    colWidths=['70%', '30%'],
                    style=TableStyle([
                        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
                    ])
                )
            )
            
            # Summary
            if 'summary' in job and job['summary']:
                elements.append(Paragraph(job['summary'], self.styles['ResumeNormal']))
            
            # Highlights
            if 'highlights' in job and job['highlights']:
                highlight_items = []
                for highlight in job['highlights']:
                    highlight_items.append(ListItem(Paragraph(highlight, self.styles['ResumeNormal'])))
                
                elements.append(ListFlowable(
                    highlight_items,
                    bulletType='bullet',
                    start=None,
                    bulletFontSize=8,
                    leftIndent=10,
                    bulletOffsetY=1
                ))
            
            elements.append(Spacer(1, 3 * mm))
        
        return elements

    def _build_education_section(self, education_items):
        """Build education section"""
        elements = []
        
        for edu in education_items:
            # Institution and dates row
            elements.append(
                Table(
                    [[Paragraph(f"<b>{edu.get('institution', '')}</b>", self.styles['JobTitle']), 
                      Paragraph(f"{edu.get('startDate', '')} - {edu.get('endDate', 'Present')}", self.styles['ResumeNormal'])]],
                    colWidths=['70%', '30%'],
                    style=TableStyle([
                        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
                    ])
                )
            )
            
            # Degree
            if 'area' in edu and 'studyType' in edu:
                elements.append(Paragraph(f"{edu['area']}, {edu['studyType']}", self.styles['ResumeNormal']))
            
            elements.append(Spacer(1, 3 * mm))
        
        return elements

    def _build_skills_section(self, skills_items):
        """Build skills section"""
        elements = []
        
        data = []
        row = []
        
        for i, skill in enumerate(skills_items):
            # Create skill cell
            skill_text = f"<b>{skill.get('name', '')}</b>"
            if 'keywords' in skill and skill['keywords']:
                skill_text += f"<br/>{', '.join(skill['keywords'])}"
            
            skill_cell = Paragraph(skill_text, self.styles['ResumeNormal'])
            row.append(skill_cell)
            
            # Create a new row after every 2 skills or at the end
            if (i + 1) % 2 == 0 or i == len(skills_items) - 1:
                # If odd number of skills, add empty cell to complete row
                if i == len(skills_items) - 1 and (i + 1) % 2 != 0:
                    row.append('')
                data.append(row)
                row = []
        
        if data:
            skill_table = Table(
                data,
                colWidths=['50%', '50%'],
                style=TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 0),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 10),
                ])
            )
            elements.append(skill_table)
            elements.append(Spacer(1, 3 * mm))
        
        return elements

    def _build_projects_section(self, projects_items):
        """Build projects section"""
        elements = []
        
        for project in projects_items:
            # Project name and dates row
            project_header = f"<b>{project.get('name', '')}</b>"
            date_range = ""
            if 'startDate' in project and 'endDate' in project:
                date_range = f"{project['startDate']} - {project['endDate']}"
            
            elements.append(
                Table(
                    [[Paragraph(project_header, self.styles['JobTitle']), 
                      Paragraph(date_range, self.styles['ResumeNormal'])]],
                    colWidths=['70%', '30%'],
                    style=TableStyle([
                        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
                    ])
                )
            )
            
            # Description
            if 'description' in project and project['description']:
                elements.append(Paragraph(project['description'], self.styles['ResumeNormal']))
            
            # Highlights
            if 'highlights' in project and project['highlights']:
                highlight_items = []
                for highlight in project['highlights']:
                    highlight_items.append(ListItem(Paragraph(highlight, self.styles['ResumeNormal'])))
                
                elements.append(ListFlowable(
                    highlight_items,
                    bulletType='bullet',
                    start=None,
                    bulletFontSize=8,
                    leftIndent=10,
                    bulletOffsetY=1
                ))
            
            elements.append(Spacer(1, 3 * mm))
        
        return elements

    async def _generate_resume(self, resume: Resume) -> str:
        """
        Generate a PDF for a resume using ReportLab.
        
        Args:
            resume: Resume object

        Returns:
            URL of the generated PDF
        """
        buffer = io.BytesIO()
        
        # Get resume data as dict
        resume_data = resume.data if isinstance(resume.data, dict) else resume.data.dict()
        metadata = resume_data.get('metadata', {})
        layout = metadata.get('layout', [{'width': 210, 'height': 297}])  # Default to A4 if no layout
        
        # Get first page size as default
        first_page_size = self._get_page_size(layout[0])
        
        # Create the PDF document
        doc = SimpleDocTemplate(
            buffer,
            pagesize=first_page_size,
            leftMargin=15*mm,
            rightMargin=15*mm,
            topMargin=15*mm,
            bottomMargin=15*mm
        )

        # Build resume content
        elements = []
        
        # Process each page
        for page_index, page_layout in enumerate(layout):
            if page_index == 0:
                # Add header only on first page
                elements.extend(self._build_header(resume_data))
            
            # Process sections for this page
            for section in resume_data.get('sections', []):
                if section.get('page', 1) == page_index + 1:  # Pages are 1-indexed in data
                    # Add section title
                    elements.append(Paragraph(section.get('title', ''), self.styles['SectionTitle']))
                    elements.append(Spacer(1, 2 * mm))
                    
                    # Add section content based on type
                    if section.get('type') == 'work' and 'work' in resume_data:
                        elements.extend(self._build_work_section(resume_data['work']))
                        
                    elif section.get('type') == 'education' and 'education' in resume_data:
                        elements.extend(self._build_education_section(resume_data['education']))
                        
                    elif section.get('type') == 'skills' and 'skills' in resume_data:
                        elements.extend(self._build_skills_section(resume_data['skills']))
                        
                    elif section.get('type') == 'projects' and 'projects' in resume_data:
                        elements.extend(self._build_projects_section(resume_data['projects']))
                        
                    elif section.get('type') == 'custom' and 'content' in section:
                        # For custom sections, we'd need to convert HTML to ReportLab elements
                        # For simplicity, just adding as-is with some basic HTML support
                        elements.append(Paragraph(section['content'], self.styles['ResumeNormal']))
                        elements.append(Spacer(1, 3 * mm))
            
            # Add page break after each page except the last
            if page_index < len(layout) - 1:
                elements.append(Flowable.PageBreak())
        
        # Build the PDF
        doc.build(elements)
        
        # Get PDF bytes
        buffer.seek(0)
        pdf_bytes = buffer.getvalue()
        
        # Upload the PDF to storage
        url = storage_service.upload_object(
            user_id=resume.userId,
            type_="resumes",
            file_data=pdf_bytes,
            filename=f"{resume.slug}.pdf"
        )
        
        return url

    async def _generate_preview(self, resume: Resume) -> str:
        """
        Generate a preview image for a resume using ReportLab and Pillow.
        
        Args:
            resume: Resume object
            
        Returns:
            URL of the generated preview
        """
        # Generate PDF first
        buffer = io.BytesIO()
        
        # Get resume data as dict
        resume_data = resume.data if isinstance(resume.data, dict) else resume.data.dict()
        metadata = resume_data.get('metadata', {})
        layout = metadata.get('layout', [{'width': 210, 'height': 297}])  # Default to A4 if no layout
        
        # Get first page size
        first_page_size = self._get_page_size(layout[0])
        
        # Create the PDF document - first page only
        doc = SimpleDocTemplate(
            buffer,
            pagesize=first_page_size,
            leftMargin=15*mm,
            rightMargin=15*mm,
            topMargin=15*mm,
            bottomMargin=15*mm
        )

        # Build resume content for first page
        elements = []
        
        # Add header
        elements.extend(self._build_header(resume_data))
        
        # Process sections for first page only
        for section in resume_data.get('sections', []):
            if section.get('page', 1) == 1:  # Only first page
                # Add section title
                elements.append(Paragraph(section.get('title', ''), self.styles['SectionTitle']))
                elements.append(Spacer(1, 2 * mm))
                
                # Add section content based on type
                if section.get('type') == 'work' and 'work' in resume_data:
                    elements.extend(self._build_work_section(resume_data['work']))
                    
                elif section.get('type') == 'education' and 'education' in resume_data:
                    elements.extend(self._build_education_section(resume_data['education']))
                    
                elif section.get('type') == 'skills' and 'skills' in resume_data:
                    elements.extend(self._build_skills_section(resume_data['skills']))
                    
                elif section.get('type') == 'projects' and 'projects' in resume_data:
                    elements.extend(self._build_projects_section(resume_data['projects']))
                    
                elif section.get('type') == 'custom' and 'content' in section:
                    elements.append(Paragraph(section['content'], self.styles['ResumeNormal']))
                    elements.append(Spacer(1, 3 * mm))
        
        # Build the PDF
        doc.build(elements)
        
        # Get PDF bytes
        buffer.seek(0)
        pdf_bytes = buffer.getvalue()
        
        # Convert PDF to JPEG image using pdf2image
        try:
            from pdf2image import convert_from_bytes
            
            images = convert_from_bytes(
                pdf_bytes, 
                dpi=150,
                first_page=1,
                last_page=1
            )
            
            img_byte_arr = io.BytesIO()
            images[0].save(img_byte_arr, format='JPEG', quality=80)
            img_byte_arr.seek(0)
            screenshot = img_byte_arr.getvalue()
            
        except ImportError:
            logger.warning("pdf2image not installed, using PDF as preview")
            screenshot = pdf_bytes
        
        # Upload the preview image
        url = storage_service.upload_object(
            user_id=resume.userId,
            type_="previews",
            file_data=screenshot,
            filename=str(resume.id)
        )
        
        return url

# Singleton instance with the same name as in the original code
printer_service = PrinterService()