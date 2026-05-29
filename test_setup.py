#!/usr/bin/env python3
"""
Test script to verify all credentials and APIs are working
"""
import os
from dotenv import load_dotenv

def test_environment():
    """Check if all environment variables are set"""
    print("=" * 50)
    print("Testing Environment Variables...")
    print("=" * 50)
    
    load_dotenv()
    
    vars_to_check = [
        'TELEGRAM_BOT_TOKEN',
        'GEMINI_API_KEY',
        'GOOGLE_SHEET_NAME'
    ]
    
    all_present = True
    for var in vars_to_check:
        value = os.getenv(var)
        if value:
            print(f"✅ {var}: Set ({value[:10]}...)")
        else:
            print(f"❌ {var}: Not set")
            all_present = False
    
    if os.path.exists('credentials.json'):
        print("✅ credentials.json: Found")
    else:
        print("❌ credentials.json: Not found")
        all_present = False
    
    return all_present

def test_gemini():
    """Test Google Gemini API connection"""
    print("\n" + "=" * 50)
    print("Testing Google Gemini API...")
    print("=" * 50)
    
    try:
        from google import genai
        client = genai.Client()
        # Test with a simple prompt
        response = client.models.generate_content(
            model="models/gemini-2.5-flash",
            contents="Say 'API test successful'"
        )
        print("✅ Gemini API connected successfully")
        print(f"   Response: {response.text[:50]}...")
        return True
    except Exception as e:
        print(f"❌ Gemini test failed: {e}")
        return False

def test_google_sheets():
    """Test Google Sheets connection"""
    print("\n" + "=" * 50)
    print("Testing Google Sheets...")
    print("=" * 50)
    
    try:
        from sheets_logger import get_sheets_client
        client = get_sheets_client()
        sheet_name = os.getenv('GOOGLE_SHEET_NAME')
        sheet = client.open(sheet_name)
        print(f"✅ Connected to Google Sheet: {sheet_name}")
        print(f"   Sheet ID: {sheet.id}")
        return True
    except Exception as e:
        print(f"❌ Google Sheets test failed: {e}")
        return False

def test_telegram():
    """Test Telegram bot token"""
    print("\n" + "=" * 50)
    print("Testing Telegram Bot...")
    print("=" * 50)
    
    try:
        from telegram import Bot
        bot = Bot(token=os.getenv('TELEGRAM_BOT_TOKEN'))
        import asyncio
        async def get_me():
            me = await bot.get_me()
            return me
        
        me = asyncio.run(get_me())
        print(f"✅ Bot connected: @{me.username}")
        print(f"   Bot name: {me.first_name}")
        return True
    except Exception as e:
        print(f"❌ Telegram test failed: {e}")
        return False

def main():
    """Run all tests"""
    print("\n🔧 AskMama Bot - Setup Verification\n")
    
    results = []
    
    # Test 1: Environment
    results.append(("Environment", test_environment()))
    
    # Test 2: Gemini
    results.append(("Gemini API", test_gemini()))
    
    # Test 3: Google Sheets
    results.append(("Google Sheets", test_google_sheets()))
    
    # Test 4: Telegram
    results.append(("Telegram Bot", test_telegram()))
    
    # Summary
    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {name}")
    
    all_passed = all(r[1] for r in results)
    
    if all_passed:
        print("\n🎉 All tests passed! You're ready to run the bot.")
        print("\nRun: python run.py")
    else:
        print("\n⚠️  Some tests failed. Please check the errors above.")
        print("Refer to README.md for setup instructions.")

if __name__ == '__main__':
    main()
