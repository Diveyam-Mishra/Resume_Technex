from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks, Depends
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional, Dict, Any
import tempfile
import os
import shutil
import cv2
import numpy as np
import re
import docx
import PyPDF2
import json
import requests
import time
from pathlib import Path
import subprocess
from pydantic import BaseModel, Field
import openai
from contextlib import asynccontextmanager

import subprocess
from pydantic import BaseModel, Field
import openai
from contextlib import asynccontextmanager
user_profiles = {}
class ChatResponse(BaseModel):
    response: str
    suggestions: Optional[Dict[str, Any]] = None
    extracted_info: Optional[Dict[str, Any]] = None
# Azure OpenAI Configuration
class OpenAISettings(BaseModel):
    api_key: str = Field(..., env="AZURE_OPENAI_API_KEY")
    endpoint: str = Field(..., env="AZURE_OPENAI_ENDPOINT")
    api_version: str = Field("2023-07-01-preview", env="AZURE_OPENAI_API_VERSION")
    deployment_name: str = Field("gpt-4", env="AZURE_OPENAI_DEPLOYMENT_NAME")

async def extract_profile_info(message: str, chat_history: list, openai_client: Any):
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": """Extract structured personal/professional information from this message if present.
                Return a JSON with any of these fields that you can confidently extract:
                {
                    "name": "full name if mentioned",
                    "email": "email if mentioned",
                    "phone": "phone number if mentioned",
                    "education": "education details if mentioned",
                    "experience": "work experience if mentioned",
                    "skills": "skills if mentioned",
                    "summary": "professional summary if mentioned"
                }
                Only include fields where you found information in the message. If no information can be extracted, return an empty JSON object {}."""},
                {"role": "user", "content": f"Message: {message}\n\nExtract any profile information from this message."}
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        
        # Parse the JSON response
        extracted_info = json.loads(response.choices[0].message.content)
        return extracted_info
    except Exception as e:
        print(f"Error extracting profile info: {str(e)}")
        return {}

# Dependency to get OpenAI settings
def get_openai_settings():
    return OpenAISettings(
        api_key=os.getenv("AZURE_OPENAI_API_KEY", "your-default-key"),
        endpoint=os.getenv("AZURE_OPENAI_ENDPOINT", "your-default-endpoint"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2023-07-01-preview"),
        deployment_name=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4")
    )

# Initialize OpenAI client
def get_openai_client(settings: OpenAISettings = Depends(get_openai_settings)):
    client = openai.AzureOpenAI(
        api_key=settings.api_key,
        api_version=settings.api_version,
        azure_endpoint=settings.endpoint
    )
    return client

# Chat history storage
chat_histories = {}

# FastAPI app with lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup: Create directories if they don't exist
    TEMP_DIR.mkdir(exist_ok=True)
    Path("./templates").mkdir(exist_ok=True)
    yield
    # Cleanup: Nothing to do here for now

app = FastAPI(
    title="Resume Enhancement Bot",
    description="A bot that helps improve resumes by analyzing whitespace, checking spelling, and detecting buzzwords with Azure OpenAI integration",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create temp directory for storing files
TEMP_DIR = Path("./temp")
TEMP_DIR.mkdir(exist_ok=True)

# Define buzzwords to detect
BUZZWORDS = [
    "synergy", "leverage", "strategic", "dynamic", "proactive",
    "innovative", "ecosystem", "disruptive", "scalable", "optimization",
    "robust", "cutting-edge", "visionary", "paradigm", "streamline",
    "empower", "best-of-breed", "mission-critical", "bleeding-edge", "world-class"
]

class GrammarResponse(BaseModel):
    corrections: List[dict]
    success: bool

class WhitespaceAnalysis(BaseModel):
    original_text: str
    improved_text: Optional[str] = None
    has_excessive_whitespace: bool = False

class BuzzwordAnalysis(BaseModel):
    text: str
    buzzwords_found: List[str]
    suggestions: Optional[dict] = None

@app.post("/generate-resume-with-ai/", summary="Generate a resume with AI-enhanced content")
async def generate_resume_with_ai(
    background_tasks: BackgroundTasks,
    template_name: str = Form(...),
    user_id: str = Form(...),
    job_title: Optional[str] = Form(None),
    industry: Optional[str] = Form(None),
    experience_level: Optional[str] = Form(None),
    openai_client: Any = Depends(get_openai_client)
):
    """
    Generate a complete resume with AI filling in missing sections based on provided information.
    """
    # Create output paths
    output_id = f"{int(time.time())}"
    tex_output_path = TEMP_DIR / f"resume_{output_id}.tex"
    pdf_output_path = TEMP_DIR / f"resume_{output_id}.pdf"
    
    # Template path
    template_path = f"./templates/{template_name}.tex"
    
    if not os.path.exists(template_path):
        raise HTTPException(status_code=404, detail=f"Template '{template_name}' not found")
    
    try:
        # Retrieve existing user data from chat history and profile
        user_data = {}
        if user_id in chat_histories:
            chat_history = chat_histories[user_id]
            
            # Extract user information from chat history
            try:
                # Get all the text from chat history
                messages_text = "\n".join([msg["content"] for msg in chat_history if msg["role"] in ["user", "assistant"]])
                
                # Use profile info if available
                if user_id in user_profiles:
                    profile = user_profiles[user_id]
                    for key, value in profile.dict.items():
                        if value is not None and key != "extracted_at":
                            user_data[key] = value
                
                # Extract additional information from chat history if needed
                extraction_response = openai_client.chat.completions.create(
                    model="gpt-4",
                    messages=[
                        {"role": "system", "content": """Extract the user's resume information from this conversation history.
                        Return a JSON object with these fields if found in the conversation:
                        {
                            "name": "user's full name",
                            "email": "user's email",
                            "phone": "user's phone",
                            "education": "education details",
                            "experience": "work experience details",
                            "summary": "professional summary",
                            "skills": "skills list",
                            "interests": "user's interests or hobbies",
                            "projects": "relevant projects",
                            "certifications": "professional certifications"
                        }
                        Only include fields that you can confidently extract from the conversation."""},
                        {"role": "user", "content": f"Here's the conversation history:\n{messages_text}"}
                    ],
                    temperature=0.3,
                    response_format={"type": "json_object"}
                )
                
                # Extract user data from AI response
                extracted_data = json.loads(extraction_response.choices[0].message.content)
                
                # Merge with existing user_data (don't overwrite existing data)
                for key, value in extracted_data.items():
                    if key not in user_data or not user_data[key]:
                        user_data[key] = value
                
            except Exception as e:
                print(f"Error extracting user data from chat: {str(e)}")
        
        # Check what information we have and what's missing
        required_fields = ["name", "email", "phone", "education", "experience", "skills"]
        missing_fields = [field for field in required_fields if field not in user_data or not user_data[field]]
        
        # Generate missing fields with AI
        if missing_fields:
            context = {
                "job_title": job_title or "professional",
                "industry": industry or "general",
                "experience_level": experience_level or "mid-level",
            }
            
            # Include any information we do have
            for key, value in user_data.items():
                if value:
                    context[key] = value
            
            # Generate each missing field with AI
            for field in missing_fields:
                try:
                    field_prompt = get_field_generation_prompt(field, context)
                    
                    completion = openai_client.chat.completions.create(
                        model="gpt-4",
                        messages=[
                            {"role": "system", "content": field_prompt},
                            {"role": "user", "content": f"Generate {field} for a {context['experience_level']} {context['job_title']} in the {context['industry']} industry."}
                        ],
                        temperature=0.7,
                        max_tokens=1000
                    )
                    
                    user_data[field] = completion.choices[0].message.content
                except Exception as e:
                    print(f"Error generating {field}: {str(e)}")
                    user_data[field] = f"[Please provide your {field}]"
        
        # Always enhance or generate summary with AI
        try:
            summary_context = {**user_data, "job_title": job_title, "industry": industry}
            completion = openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": """Create a compelling professional summary for a resume.
                    The summary should be 2-3 sentences that highlight the candidate's experience, skills, and value proposition.
                    Focus on achievements and strengths relevant to their target role. Be specific and avoid clichés."""},
                    {"role": "user", "content": f"Create a professional summary for someone with these details:\n{json.dumps(summary_context, indent=2)}"}
                ],
                temperature=0.7,
                max_tokens=300
            )
            user_data["summary"] = completion.choices[0].message.content
        except Exception as e:
            print(f"Error generating summary: {str(e)}")
            user_data["summary"] = user_data.get("summary", "Experienced professional with a track record of success.")
        
        # Prepare template data
        template_data = {
            "name": user_data.get("name", ""),
            "email": user_data.get("email", ""),
            "phone": user_data.get("phone", ""),
            "education": user_data.get("education", ""),
            "experience": user_data.get("experience", ""),
            "summary": user_data.get("summary", ""),
            "skills": user_data.get("skills", "")
        }
        
        # Add optional sections if available
        for field in ["interests", "projects", "certifications"]:
            if field in user_data and user_data[field]:
                template_data[field] = user_data[field]
        
        # Insert data into template and compile
        success = insert_into_overleaf_template(template_data, template_path, tex_output_path)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to compile LaTeX template")
        
        # Update chat history to inform user about AI-generated content
        if user_id in chat_histories:
            ai_generated_fields = [field for field in missing_fields if field in user_data]
            if ai_generated_fields:
                chat_histories[user_id].append({
                    "role": "system", 
                    "content": f"System has generated the following information using AI: {', '.join(ai_generated_fields)}"
                })
                
                generated_msg = "I've generated your resume! " + (
                    f"I used AI to create content for {', '.join(ai_generated_fields)}. " if ai_generated_fields else ""
                ) + "You can review the PDF and let me know if you'd like to make any changes."
                
                chat_histories[user_id].append({
                    "role": "assistant", 
                    "content": generated_msg
                })
        
        # Schedule cleanup of temporary files
        background_tasks.add_task(lambda: os.remove(tex_output_path) if os.path.exists(tex_output_path) else None)
        background_tasks.add_task(lambda: os.remove(pdf_output_path) if os.path.exists(pdf_output_path) else None)
        
        # Return the PDF file along with information about AI-generated content
        response = FileResponse(
            path=pdf_output_path,
            filename=f"enhanced_resume.pdf",
            media_type="application/pdf"
        )
        
        response.headers["X-AI-Generated-Fields"] = ",".join(missing_fields)
        return response
    
    except Exception as e:
        # Clean up if there's an error
        if os.path.exists(tex_output_path):
            os.remove(tex_output_path)
        if os.path.exists(pdf_output_path):
            os.remove(pdf_output_path)
        raise HTTPException(status_code=500, detail=f"Error generating resume: {str(e)}")

def get_chat_session(user_id: str):
    if user_id not in chat_histories:
        chat_histories[user_id] = [
            {"role": "system", "content": """You are a friendly but strict resume assistant bot. 
            Your goal is to help users create professional resumes by providing constructive feedback
            and asking for necessary information in a conversational manner. Be helpful, concise, and friendly,
            but maintain a high standard for professional resume quality. When users provide information, 
            ask follow-up questions to ensure completeness. Your feedback should be constructive but direct.
            
            IMPORTANT: Naturally ask for and collect the following information during the conversation:
            1. The user's full name
            2. Email address
            3. Phone number
            4. Education history
            5. Work experience
            6. Skills
            7. Professional summary (if appropriate)
            
            Don't ask for all information at once. Have a natural conversation and collect this information
            gradually. Store this information as you learn it, as it will be used to generate their resume."""}
        ]
        
        # Initialize user profile
        user_profiles[user_id] = UserProfileData()
    
    return chat_histories[user_id]

def get_field_generation_prompt(field, context):
    """Get an appropriate prompt for generating a specific resume field"""
    prompts = {
        "name": "Generate a realistic full name for a professional resume.",
        
        "email": "Generate a professional email address based on the person's name or generate a realistic one if no name is provided.",
        
        "phone": "Generate a realistic phone number in the format XXX-XXX-XXXX.",
        
        "education": """Generate a realistic education section for a resume. Include:
        1. University/college name
        2. Degree earned
        3. Field of study
        4. Graduation year
        5. GPA (if applicable)
        6. Relevant coursework or honors (optional)
        
        Format it professionally as it would appear on a resume. Create 1-2 entries.""",
        
        "experience": f"""Generate realistic work experience for a {context.get('experience_level', 'mid-level')} {context.get('job_title', 'professional')} in the {context.get('industry', 'technology')} industry.
        
        For each position include:
        1. Job title
        2. Company name
        3. Employment dates (month/year format)
        4. 3-5 bullet points highlighting responsibilities and achievements
        
        Make the achievements specific and quantified where possible.
        Use strong action verbs at the beginning of bullets.
        Include keywords relevant to the industry.
        Create 2-3 positions showing career progression.""",
        
        "skills": f"""Generate a comprehensive skills section for a {context.get('job_title', 'professional')} in the {context.get('industry', 'technology')} industry.
        
        Include:
        1. Technical skills (software, tools, programming languages if relevant)
        2. Industry-specific skills
        3. Soft skills (3-5 most relevant ones)
        
        Format as a clean, organized list appropriate for a resume.""",
    }
    
    return prompts.get(field, f"Generate realistic content for the {field} section of a professional resume.")
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional, Dict, Any
import tempfile
import os
import shutil
import cv2
import numpy as np
import re
import docx
import PyPDF2
import json
import requests
import time
from pathlib import Path


async def analyze_whitespace(text, openai_client=None):
    """
    Analyze if text has excessive whitespace issues, with AI enhancement if client provided
    """
    # Basic detection
    excessive_spaces = bool(re.search(r'[^\n]\s{2,}[^\n]', text))
    excessive_newlines = bool(re.search(r'\n{3,}', text))
    
    result = WhitespaceAnalysis(
        original_text=text,
        has_excessive_whitespace=(excessive_spaces or excessive_newlines)
    )
    
    if result.has_excessive_whitespace:
        if openai_client:
            # Use Azure OpenAI for intelligent whitespace fixing
            try:
                response = openai_client.chat.completions.create(
                    model="gpt-4",  # Use deployment name here
                    messages=[
                        {"role": "system", "content": "You are a professional resume editor. Fix only whitespace issues in the text below, preserving all content but ensuring consistent formatting. Be strict about professional standards but make minimal changes."},
                        {"role": "user", "content": f"Fix whitespace issues in this text while preserving all content: {text}"}
                    ],
                    temperature=0.3,
                    max_tokens=1024
                )
                result.improved_text = response.choices[0].message.content
            except Exception as e:
                # Fallback to basic approach if API fails
                improved = re.sub(r'[ \t]{2,}', ' ', text)
                improved = re.sub(r'\n{3,}', '\n\n', improved)
                result.improved_text = improved
        else:
            # Basic approach without AI
            improved = re.sub(r'[ \t]{2,}', ' ', text)
            improved = re.sub(r'\n{3,}', '\n\n', improved)
            result.improved_text = improved
    
    return result

async def check_grammar(text, openai_client=None):
    """
    Check grammar and spelling using Azure OpenAI
    """
    corrections = []
    
    if openai_client:
        try:
            # Use Azure OpenAI for comprehensive grammar checking
            response = openai_client.chat.completions.create(
                model="gpt-4",  # Use deployment name here
                messages=[
                    {"role": "system", "content": """You are a strict professional resume editor. 
                    Analyze the text for grammar, spelling, and professional language issues.
                    Return only a JSON array of corrections with the following structure:
                    [{"original": "incorrect text", "suggestion": "corrected text", "type": "spelling|grammar|word_choice|punctuation", "explanation": "brief explanation"}]
                    Be thorough but focus only on clear errors, not stylistic preferences. Empty array if no issues found."""},
                    {"role": "user", "content": f"Check this text for grammar and professional language issues: {text}"}
                ],
                temperature=0.3,
                response_format={"type": "json_object"}
            )
            
            try:
                # Parse the JSON response
                corrections_json = json.loads(response.choices[0].message.content)
                if "corrections" in corrections_json:
                    corrections = corrections_json["corrections"]
                else:
                    # Handle case where the model returned a different JSON structure
                    for key, value in corrections_json.items():
                        if isinstance(value, list) and len(value) > 0 and "original" in value[0]:
                            corrections = value
                            break
            except (json.JSONDecodeError, KeyError):
                # Fallback to basic approach if parsing fails
                pass
                
        except Exception as e:
            # Fallback to basic checking if API fails
            # Check for common spelling mistakes
            misspellings = {
                "recieve": "receive",
                "seperate": "separate",
                "accomodate": "accommodate",
                "occured": "occurred",
                "refered": "referred",
                "definately": "definitely",
                "liason": "liaison",
                "preformance": "performance",
                "managment": "management"
            }
            
            for word, correction in misspellings.items():
                if word in text.lower():
                    corrections.append({
                        "original": word,
                        "suggestion": correction,
                        "type": "spelling",
                        "explanation": "Common spelling error"
                    })
    else:
        # Basic check without AI
        misspellings = {
            "recieve": "receive",
            "seperate": "separate",
            "accomodate": "accommodate",
            "occured": "occurred",
            "refered": "referred"
        }
        
        for word, correction in misspellings.items():
            if word in text.lower():
                corrections.append({
                    "original": word,
                    "suggestion": correction,
                    "type": "spelling",
                    "explanation": "Common spelling error"
                })
    
    return GrammarResponse(corrections=corrections, success=True)

async def detect_buzzwords(text, openai_client=None):
    """
    Detect buzzwords in the text and suggest alternatives using Azure OpenAI
    """
    # Start with a base buzzword list
    text_lower = text.lower()
    found = []
    suggestions = {}
    
    if openai_client:
        try:
            # Use Azure OpenAI for comprehensive buzzword detection and alternatives
            response = openai_client.chat.completions.create(
                model="gpt-4",  # Use deployment name here
                messages=[
                    {"role": "system", "content": """You are a strict professional resume reviewer. 
                    Analyze the text for business buzzwords, clichés and vague terminology that weakens resumes.
                    Return only a JSON object with the following structure:
                    {"buzzwords_found": ["word1", "word2"], "suggestions": {"word1": "better alternative", "word2": "better alternative"}}
                    Be strict but fair - focus on clear buzzwords that hiring managers dislike. 
                    Common buzzwords include: synergy, leverage, strategic, dynamic, proactive, innovative, 
                    ecosystem, disruptive, scalable, optimization, robust, cutting-edge, visionary, paradigm, 
                    streamline, empower, best-of-breed, mission-critical, bleeding-edge, world-class.
                    Empty arrays if no issues found."""},
                    {"role": "user", "content": f"Analyze this text for resume buzzwords and suggest alternatives: {text}"}
                ],
                temperature=0.3,
                response_format={"type": "json_object"}
            )
            
            try:
                # Parse the JSON response
                buzzword_json = json.loads(response.choices[0].message.content)
                if "buzzwords_found" in buzzword_json and "suggestions" in buzzword_json:
                    found = buzzword_json["buzzwords_found"]
                    suggestions = buzzword_json["suggestions"]
            except (json.JSONDecodeError, KeyError):
                # Fallback to basic approach if parsing fails
                pass
                
        except Exception as e:
            # Fallback to basic buzzword detection if API fails
            for word in BUZZWORDS:
                if word in text_lower:
                    found.append(word)
            
            if found:
                buzzword_alternatives = {
                    "synergy": "collaboration",
                    "leverage": "use",
                    "strategic": "planned",
                    "dynamic": "flexible",
                    "proactive": "anticipatory",
                    "innovative": "creative",
                    "ecosystem": "environment",
                    "disruptive": "groundbreaking",
                    "scalable": "adaptable",
                    "optimization": "improvement",
                    "robust": "strong",
                    "cutting-edge": "advanced",
                    "visionary": "forward-thinking",
                    "paradigm": "model",
                    "streamline": "simplify",
                    "empower": "enable",
                    "best-of-breed": "high-quality",
                    "mission-critical": "essential",
                    "bleeding-edge": "newest",
                    "world-class": "excellent"
                }
                
                for word in found:
                    if word in buzzword_alternatives:
                        suggestions[word] = buzzword_alternatives[word]
    else:
        # Basic buzzword detection without AI
        for word in BUZZWORDS:
            if word in text_lower:
                found.append(word)
        
        if found:
            buzzword_alternatives = {
                "synergy": "collaboration",
                "leverage": "use",
                "strategic": "planned",
                "dynamic": "flexible",
                "proactive": "anticipatory"
            }
            
            for word in found:
                if word in buzzword_alternatives:
                    suggestions[word] = buzzword_alternatives[word]
    
    return BuzzwordAnalysis(
        text=text,
        buzzwords_found=found,
        suggestions=suggestions if found else None
    )

def extract_text_from_docx(file_path):
    """Extract text from a .docx file"""
    doc = docx.Document(file_path)
    return "\n".join([paragraph.text for paragraph in doc.paragraphs])

def extract_text_from_pdf(file_path):
    """Extract text from a PDF file"""
    text = ""
    with open(file_path, "rb") as file:
        reader = PyPDF2.PdfReader(file)
        for page_num in range(len(reader.pages)):
            text += reader.pages[page_num].extract_text()
    return text

def insert_into_overleaf_template(data, template_path, output_path):
    """Insert data into an Overleaf LaTeX template and compile it"""
    try:
        # Read the template
        with open(template_path, 'r') as file:
            template_content = file.read()
        
        # Replace placeholders with actual data
        for key, value in data.items():
            placeholder = f"{{{{{key}}}}}"
            print(f"Processing key: {key}, type: {type(value)}")
            
            # Safely handle the value based on its type
            if isinstance(value, list):
                # Check if the list contains dictionaries with expected structure
                if value and isinstance(value[0], dict) and 'project' in value[0] and 'details' in value[0]:
                    formatted_value = "\n\n".join([f"{entry['project']}\n{entry['details']}" for entry in value])
                elif not value:
                    template_content = template_content.replace(placeholder, "")
                else:
                    # Simple list of items
                    formatted_value = "\n".join([str(item) for item in value])
                template_content = template_content.replace(placeholder, formatted_value)
            else:
                # Ensure value is a string before replacing
                template_content = template_content.replace(placeholder,str(value))
        tex_file_path = output_path.replace('.pdf', '.tex')
        # Write to output file
        with open(tex_file_path, 'w') as f:
            f.write(template_content)
        
        # Compile the LaTeX file to PDF
        cmd = ['pdflatex', '-interaction', 'nonstopmode', tex_file_path]
        proc = subprocess.Popen(cmd)
        proc.communicate()
        
        retcode = proc.returncode
        if retcode != 0:
            print(f"LaTeX Error")
            if os.path.exists(output_path):
                os.unlink(output_path)
            return False
        
        # Cleanup temporary files
        for ext in ['.tex', '.log', '.aux']:
            temp_file = output_path.replace('.pdf', ext)
            if os.path.exists(temp_file):
                os.unlink(temp_file)
        
        return True
    
    except Exception as e:
        print(f"Error creating PDF with LaTeX: {str(e)}")
        return False

# Chat models
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    user_id: str
    message: str

class UserProfileData(BaseModel):
    """Model for tracking user profile information extracted from chat"""
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    education: Optional[str] = None
    experience: Optional[str] = None
    summary: Optional[str] = None
    skills: Optional[str] = None
    extracted_at: Optional[float] = None
    
class ChatResponse(BaseModel):
    response: str
    suggestions: Optional[Dict[str, Any]] = None

# Create or get chat session
def get_chat_session(user_id: str):
    if user_id not in chat_histories:
        chat_histories[user_id] = [
            {"role": "system", "content": """You are a friendly but strict resume assistant bot. 
            Your goal is to help users create professional resumes by providing constructive feedback
            and asking for necessary information in a conversational manner. Be helpful, concise, and friendly,
            but maintain a high standard for professional resume quality. When users provide information, 
            ask follow-up questions to ensure completeness. Your feedback should be constructive but direct."""}
        ]
    return chat_histories[user_id]

@app.post("/chat/", summary="Chat with the resume bot")
async def chat_with_bot(
    request: ChatRequest,
    openai_client: Any = Depends(get_openai_client)
):
    user_id = request.user_id
    chat_history = get_chat_session(user_id)
    user_profile = user_profiles.get(user_id)
    
    # Extract profile information from user message
    extracted_info = await extract_profile_info(request.message, chat_history, openai_client)
    
    # Update user profile with extracted information
    if extracted_info and user_profile:
        for key, value in extracted_info.items():
            if value and hasattr(user_profile, key):
                setattr(user_profile, key, value)
        
        # Update extraction timestamp
        user_profile.extracted_at = time.time()
    
    # Add user message to history
    chat_history.append({"role": "user", "content": request.message})
    
    # Add profile information as context for the AI
    profile_context = ""
    if user_profile:
        filled_fields = []
        missing_fields = []
        
        for field in ["name", "email", "phone", "education", "experience"]:
            value = getattr(user_profile, field, None)
            if value:
                filled_fields.append(field)
            else:
                missing_fields.append(field)
        
        if filled_fields:
            profile_context += f"User has provided: {', '.join(filled_fields)}. "
        if missing_fields:
            profile_context += f"Still need to collect: {', '.join(missing_fields)}. "
    
    if profile_context:
        chat_history.append({"role": "system", "content": profile_context})
    
    # Generate response
    response = openai_client.chat.completions.create(
        model="gpt-4",  # Use deployment name here
        messages=chat_history,
        temperature=0.7,
        max_tokens=800
    )
    
    bot_response = response.choices[0].message.content
    
    # Remove the temporary profile context message if it was added
    if profile_context:
        chat_history.pop()
    
    # Add bot response to history
    chat_history.append({"role": "assistant", "content": bot_response})
    
    # Extract suggestions if the bot is asking for specific information
    suggestions = None
    if "experience" in bot_response.lower() or "education" in bot_response.lower() or "skill" in bot_response.lower():
        try:
            suggestion_response = openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "Extract what information the assistant is asking for from the user. Return a JSON with fields 'asking_for' (array of strings like 'education', 'experience', 'skills', etc) and 'specific_questions' (array of specific questions being asked)."},
                    {"role": "user", "content": bot_response}
                ],
                temperature=0.3,
                response_format={"type": "json_object"}
            )
            suggestions = json.loads(suggestion_response.choices[0].message.content)
        except:
            pass
    
    # Return the extracted profile info in the response for frontend use
    extracted_profile = None
    if user_profile:
        extracted_profile = {k: v for k, v in user_profile._dict_.items() if v is not None and k != "extracted_at"}
    
    return ChatResponse(
        response=bot_response, 
        suggestions=suggestions,
        extracted_info=extracted_profile
    )

@app.post("/analyze-resume/", summary="Upload and analyze a resume")
async def analyze_resume(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    education: str = Form(...),
    experience: str = Form(...),
    user_id: Optional[str] = Form(None),
    openai_client: Any = Depends(get_openai_client)
):
    # Create a temporary file
    temp_file_path = TEMP_DIR / file.filename
    
    try:
        # Save the uploaded file
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Extract text based on file type
        file_extension = os.path.splitext(file.filename)[1].lower()
        if file_extension == ".docx":
            text = extract_text_from_docx(temp_file_path)
        elif file_extension == ".pdf":
            text = extract_text_from_pdf(temp_file_path)
        else:
            raise HTTPException(status_code=400, detail="Unsupported file format. Please upload a .docx or .pdf file.")
        
        # Analyze whitespace with AI assistance
        whitespace_analysis = await analyze_whitespace(text, openai_client)
        
        # Check grammar with AI assistance
        grammar_check = await check_grammar(text, openai_client)
        
        # Detect buzzwords with AI assistance
        buzzword_analysis = await detect_buzzwords(text, openai_client)
        
        # Get overall AI feedback on the resume
        overall_feedback = ""
        try:
            response = openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": """You are a strict but helpful professional resume reviewer.
                    Review this resume content and provide concise, actionable feedback focusing on these areas:
                    1. Content quality and impact statements
                    2. Professional language and tone
                    3. Clarity and organization
                    
                    Be direct and specific but remain constructive. Suggest specific improvements
                    rather than just pointing out flaws. Limit your response to 3-5 sentences."""},
                    {"role": "user", "content": f"Name: {name}\nEducation: {education}\nExperience: {experience}\n\nFull Text: {text}"}
                ],
                temperature=0.5,
                max_tokens=300
            )
            overall_feedback = response.choices[0].message.content
        except Exception as e:
            overall_feedback = "Resume analysis completed. Review the detailed findings below."
        
        # Organize form data for template insertion
        template_data = {
            "name": name,
            "email": email,
            "phone": phone,
            "education": education,
            "experience": experience
        }
        
        # Add to chat history if user_id provided
        if user_id:
            chat_history = get_chat_session(user_id)
            chat_history.append({"role": "system", "content": f"The user has uploaded a resume. Here's the content: {text}"})
            chat_history.append({"role": "assistant", "content": f"I've analyzed your resume. {overall_feedback}"})
        
        # Schedule cleanup of temporary files after response is sent
        background_tasks.add_task(lambda: os.remove(temp_file_path) if os.path.exists(temp_file_path) else None)
        
        return {
            "filename": file.filename,
            "whitespace_analysis": whitespace_analysis,
            "grammar_check": grammar_check,
            "buzzword_analysis": buzzword_analysis,
            "form_data": template_data,
            "overall_feedback": overall_feedback
        }
    
    except Exception as e:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")

@app.post("/generate-resume/", summary="Generate an improved resume using Overleaf template")
async def generate_resume(
    background_tasks: BackgroundTasks,
    template_name: str = Form(...),
    user_id: str = Form(...),
    name: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    education: Optional[str] = Form(None),
    experience: Optional[str] = Form(None),
    summary: Optional[str] = Form(None),
    skills: Optional[str] = Form(None),
    openai_client: Any = Depends(get_openai_client)
):
    # Create output paths
    output_id = f"{int(time.time())}"
    tex_output_path = TEMP_DIR / f"resume_{output_id}.tex"
    pdf_output_path = TEMP_DIR / f"resume_{output_id}.pdf"
    
    # Example template path - in production, you'd have multiple templates to choose from
    template_path = f"./templates/{template_name}.tex"
    
    if not os.path.exists(template_path):
        raise HTTPException(status_code=404, detail=f"Template '{template_name}' not found")
    
    try:
        # First, extract user data from chat history if available
        user_data = {}
        if user_id in chat_histories:
            chat_history = chat_histories[user_id]
            
            # Extract user information from chat history
            try:
                # Use AI to extract structured information from chat history
                messages_text = "\n".join([msg["content"] for msg in chat_history if msg["role"] in ["user", "assistant"]])
                
                extraction_response = openai_client.chat.completions.create(
                    model="gpt-4",
                    messages=[
                        {"role": "system", "content": """Extract the user's resume information from this conversation history.
                        Return a JSON object with these fields if found in the conversation:
                        {
                            "name": "user's full name",
                            "email": "user's email",
                            "phone": "user's phone",
                            "education": "education details",
                            "experience": "work experience details",
                            "summary": "professional summary",
                            "skills": "skills list"
                        }
                        Only include fields that you can confidently extract from the conversation.
                        If a field is not mentioned in the conversation, don't include it in the JSON."""},
                        {"role": "user", "content": f"Here's the conversation history:\n{messages_text}"}
                    ],
                    temperature=0.3,
                    response_format={"type": "json_object"}
                )
                
                # Extract user data from AI response
                extracted_data = json.loads(extraction_response.choices[0].message.content)
                user_data = extracted_data
            except Exception as e:
                print(f"Error extracting user data from chat: {str(e)}")
        
        # Merge extracted data with form data (form data takes precedence if both exist)
        final_name = name or user_data.get("name", "")
        final_email = email or user_data.get("email", "")
        final_phone = phone or user_data.get("phone", "")
        final_education = education or user_data.get("education", "")
        final_experience = experience or user_data.get("experience", "")
        final_summary = summary or user_data.get("summary", "")
        final_skills = skills or user_data.get("skills", "")
        
        # Verify that required fields are present
        if not final_name or not final_email or not final_phone:
            # Try to prompt the user for missing information
            missing_fields = []
            if not final_name: missing_fields.append("name")
            if not final_email: missing_fields.append("email")
            if not final_phone: missing_fields.append("phone")
            
            if user_id in chat_histories:
                chat_histories[user_id].append({
                    "role": "assistant",
                    "content": f"I need some additional information before generating your resume. Please provide your {', '.join(missing_fields)}."
                })
            
            raise HTTPException(
                status_code=400, 
                detail=f"Missing required information: {', '.join(missing_fields)}. Please provide this information in the chat or form."
            )
        
        # Use Azure OpenAI to enhance content if possible
        enhanced_summary = final_summary or ""
        enhanced_skills = final_skills or ""
        enhanced_education = final_education
        enhanced_experience = final_experience
        
        try:
            # Enhance experience section with AI
            if experience:
                response = openai_client.chat.completions.create(
                    model="gpt-4",
                    messages=[
                        {"role": "system", "content": """You are a strict professional resume editor. 
                        Improve the experience section by:
                        1. Using strong action verbs at the beginning of bullet points
                        2. Including quantifiable achievements where possible
                        3. Removing filler words and buzzwords
                        4. Ensuring consistent formatting
                        
                        Maintain the same facts, roles, and timeline - only improve how they're presented.
                        Be direct, concise, and professional."""},
                        {"role": "user", "content": f"Improve this experience section while keeping the same information: {experience}"}
                    ],
                    temperature=0.4,
                    max_tokens=800
                )
                enhanced_experience = response.choices[0].message.content
                
            # Enhance summary if provided
            if summary:
                response = openai_client.chat.completions.create(
                    model="gpt-4",
                    messages=[
                        {"role": "system", "content": """You are a professional resume editor.
                        Create a concise, impactful professional summary that:
                        1. Highlights key strengths
                        2. Avoids clichés and buzzwords
                        3. Is tailored to the person's experience
                        4. Is 2-3 sentences maximum
                        
                        The tone should be confident but not arrogant, professional but not bland."""},
                        {"role": "user", "content": f"Name: {name}\nExperience: {experience}\nCurrent summary: {summary}\n\nCreate an improved professional summary."}
                    ],
                    temperature=0.4,
                    max_tokens=200
                )
                enhanced_summary = response.choices[0].message.content
        except Exception as e:
            # If enhancement fails, use original content
            pass
        
        # Prepare data for template
        template_data = {
            "name": final_name,
            "email": final_email,
            "phone": final_phone,
            "education": enhanced_education,
            "experience": enhanced_experience,
            "summary": enhanced_summary,
            "skills": enhanced_skills
        }
        
        # Check for whitespace issues in all text fields using async version
        for key, value in template_data.items():
            if isinstance(value, str) and value:
                whitespace_check = await analyze_whitespace(value, openai_client)
                if whitespace_check.has_excessive_whitespace:
                    template_data[key] = whitespace_check.improved_text
        
        # Insert data into template and compile
        success = insert_into_overleaf_template(template_data, template_path, tex_output_path)
        
        # Update chat history if user_id provided
        if user_id and user_id in chat_histories:
            chat_history = chat_histories[user_id]
            chat_history.append({
                "role": "system", 
                "content": "User has generated their resume PDF with your suggestions."
            })
            chat_history.append({
                "role": "assistant", 
                "content": "Great! I've generated your enhanced resume. The PDF has been created with all the improvements we discussed. Is there anything specific about the resume you'd like to discuss or modify further?"
            })
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to compile LaTeX template")
        
        # Schedule cleanup of temporary files
        background_tasks.add_task(lambda: os.remove(tex_output_path) if os.path.exists(tex_output_path) else None)
        background_tasks.add_task(lambda: os.remove(pdf_output_path) if os.path.exists(pdf_output_path) else None)
        
        # Return the PDF file
        return FileResponse(
            path=pdf_output_path,
            filename=f"enhanced_resume.pdf",
            media_type="application/pdf"
        )
    
    except Exception as e:
        # Clean up if there's an error
        if os.path.exists(tex_output_path):
            os.remove(tex_output_path)
        if os.path.exists(pdf_output_path):
            os.remove(pdf_output_path)
        raise HTTPException(status_code=500, detail=f"Error generating resume: {str(e)}")

@app.post("/accept-suggestions/", summary="Accept whitespace or grammar suggestions")
async def accept_suggestions(
    original_text: str = Form(...),
    improved_text: str = Form(...),
    type: str = Form(...),  # "whitespace", "grammar", or "buzzword"
    user_id: Optional[str] = Form(None),
    openai_client: Any = Depends(get_openai_client)
):
    # Log the accepted suggestion to chat history if user_id provided
    if user_id and user_id in chat_histories:
        chat_history = chat_histories[user_id]
        
        # Add system message about the accepted suggestion
        chat_history.append({
            "role": "system", 
            "content": f"User accepted a {type} suggestion: '{original_text}' was changed to '{improved_text}'"
        })
        
        # Add friendly confirmation from assistant
        try:
            response = openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": f"The user has accepted your suggestion to change '{original_text}' to '{improved_text}'. Acknowledge this briefly in a friendly, encouraging way without being verbose."},
                    {"role": "user", "content": "I've accepted your suggestion."}
                ],
                temperature=0.7,
                max_tokens=100
            )
            chat_history.append({"role": "assistant", "content": response.choices[0].message.content})
        except Exception:
            chat_history.append({"role": "assistant", "content": f"Great choice! I've updated '{original_text}' to '{improved_text}'."})
    
    # In a real application, you might want to log these decisions to improve your algorithms
    return {
        "success": True,
        "type": type,
        "original": original_text,
        "improved": improved_text
    }

if __name__ == "_main_":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

