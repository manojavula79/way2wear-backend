import asyncio
from openai import AsyncOpenAI
import os
from dotenv import load_dotenv

load_dotenv()

async def test_dalle():
    api_key = os.getenv("OPENAI_API_KEY")
    print(f"✅ Key loaded: {api_key[:20]}...\n" if api_key else "❌ NO KEY")
    
    try:
        client = AsyncOpenAI(api_key=api_key)
        
        prompt = "A professional outfit: men's polo shirt and joggers, high-end fashion photography"
        
        print(f"Testing GPT-Image-2...")
        print(f"Prompt: {prompt}\n")
        
        # ✅ No response_format parameter
        response = await client.images.generate(
            model="gpt-image-2",
            prompt=prompt,
            size="1024x1024",
            n=1,
        )
        
        print(f"✅ Response received!")
        
        if response.data and len(response.data) > 0:
            b64_data = response.data[0].b64_json
            
            if b64_data:
                # Convert to data URL
                data_url = f"data:image/png;base64,{b64_data[:50]}..."
                print(f"\n✅ SUCCESS! Base64 image received")
                print(f"Data URL (first 50 chars): {data_url}")
                print(f"\n✅ Image can be displayed with: <img src='data:image/png;base64,{b64_data[:30]}...' />")
            else:
                print(f"❌ b64_json is None")
        else:
            print(f"❌ No data in response")
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()

asyncio.run(test_dalle())