"""
Audio transcription using Google Gemini API
"""
import os
from google import genai

def transcribe_audio(audio_path: str) -> str:
    """
    Transcribe audio file using Google Gemini API.
    
    Args:
        audio_path: Path to the audio file
        
    Returns:
        Transcribed text
    """
    try:
        # Initialize client (automatically uses GEMINI_API_KEY env variable)
        client = genai.Client()
        
        # Upload audio file
        audio_file = client.files.upload(file=audio_path)
        
        # Generate transcription
        prompt = """Transcribe this audio accurately. Pay special attention to:

MUSICAL INSTRUMENTS:
- Erhu (Chinese two-stringed instrument, sounds like "air-who" or "er-hu")
- Guitar, Piano, Violin, Drums, etc.

COMMON PHRASES:
- "I want to take/need/get [number] [item]"
- Numbers: 1, 2, 3, etc.

Provide ONLY the transcription. Use proper spelling for instrument names."""
        
        response = client.models.generate_content(
            model="models/gemini-2.5-flash",
            contents=[prompt, audio_file]
        )
        
        transcription = response.text.strip()
        print(f"🎤 Transcription result: {transcription}")
        
        return transcription
    except Exception as e:
        raise Exception(f"Transcription failed: {str(e)}")
