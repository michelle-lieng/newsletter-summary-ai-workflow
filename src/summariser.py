import os
from typing import List, Dict
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

class Summariser():
    @staticmethod
    def generate_summary(chunks: List[Dict]) -> str:
        content = []
        for chunk in chunks:
            content.append(chunk["content"])
        
        # Configure Gemini with your API key
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])

        # Create a model with system instructions and generation config
        model = genai.GenerativeModel(
            model_name="gemini-2.0-flash",
            system_instruction=f"""
            You are a helpful newsletter summariser. This is content
            that is related to the users interests: 
            <{content}>
            You are educational and you do not add any additional information.
            """,
            generation_config={
                "max_output_tokens": 1000,   # cap response length (~words×4 = tokens)
                "temperature": 0.2,        # creativity
                #"top_p": 0.9,              # nucleus sampling
                #"top_k": 40                # top-k sampling
            }
        )

        # Generate a response with the user prompt
        resp = model.generate_content("Summarize the findings into a straightforward and easy to read format.")
        return resp.text
