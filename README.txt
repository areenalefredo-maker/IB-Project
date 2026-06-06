IB Exam Booklet Generator
=========================

SETUP (one time only):
-----------------------
1. Make sure Python 3 is installed (it comes pre-installed on Mac/Linux)
2. Download both files to the same folder:
   - server.py
   - index.html

HOW TO RUN:
-----------
Step 1: Open a terminal in the folder containing the files

Step 2: Start the proxy server:
   python3 server.py

   You will see:
   ╔══════════════════════════════════════════╗
   ║   IB Exam Generator - Proxy Server       ║
   ╚══════════════════════════════════════════╝

Step 3: Open index.html in your browser (double-click it)

Step 4: Enter your Anthropic API key (from console.anthropic.com)

Step 5: Upload your QP and MS PDF files, configure settings, generate!

NOTES:
------
- Keep the terminal open while using the tool
- Press Ctrl+C in the terminal to stop the server when done
- Your API key never leaves your machine
- Works on Windows, Mac, and Linux

WHY THE PROXY?
--------------
Browsers block direct API calls from local files for security.
The proxy server (server.py) runs locally and forwards requests to Anthropic.
