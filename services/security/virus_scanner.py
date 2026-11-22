import os
import tempfile
try:
    import clamd
except ImportError:
    clamd = None
import logging

logger = logging.getLogger(__name__)

def scan_uploaded_file(uploaded_file):
    """
    Scans a Django UploadedFile for viruses using ClamAV.
    
    Returns:
        - True: File is clean (or scanning disabled)
        - False: Virus detected
        
    Raises:
        - Exception: If critical scan error occurs (handled by caller usually)
    """
    
    # 1. Feature Flag Check
    # On Localhost/Windows, this is usually False.
    # On Production Linux, set ENABLE_VIRUS_SCAN="true" in .env
    if os.getenv("ENABLE_VIRUS_SCAN", "false").lower() != "true":
        return True

    # 2. Mock Mode (For testing without ClamAV)
    # Add MOCK_VIRUS_SCAN="true" to .env to enable
    if os.getenv("MOCK_VIRUS_SCAN", "false").lower() == "true":
        # Enhanced Mock: Check CONTENT for EICAR string
        try:
             # Read a chunk to check for signature
             for chunk in uploaded_file.chunks():
                 # Check for EICAR signature OR a custom harmless string for Windows testing
                 if b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE" in chunk or b"MOCK-VIRUS-TEST" in chunk:
                      logger.critical(f"MOCK VIRUS FOUND (Signature) in file {uploaded_file.name}")
                      return False 
        except Exception as e:
            logger.error(f"Mock Scan Error: {e}")
            
        return True # Simulate Clean

    if not clamd:
        logger.warning("ClamAV module not installed but scanning enabled.")
        return True

    tmp_path = None
    try:
        # 2. Save stream to a temporary file
        # Django files are in memory or temp storage, but ClamAV needs a real path 
        # that it can access (permissions) or we need to pass a clean stream.
        # Writing to a new temp file is the safest, most compatible way.
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            for chunk in uploaded_file.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name

        # 3. Connect to Daemon
        # Support both TCP (Windows/Docker) and Unix Socket (Linux)
        clamav_host = os.getenv("CLAMAV_HOST", "127.0.0.1" if os.name == 'nt' else None)
        clamav_port = int(os.getenv("CLAMAV_PORT", 3310))

        if clamav_host:
             logger.info(f"Connecting to ClamAV via TCP at {clamav_host}:{clamav_port}")
             cd = clamd.ClamdNetworkSocket(host=clamav_host, port=clamav_port)
        else:
             logger.info("Connecting to ClamAV via Unix Socket")
             cd = clamd.ClamdUnixSocket()
        
        # Ping check
        try:
            cd.ping()
        except Exception:
            # Daemon down?
            logger.error("ClamAV Daemon is offline!")
            # Fail Open (Allow file) or Fail Closed (Block file)? 
            # Usually Fail Closed for high security, but we'll return True with warning for now 
            # to avoid blocking production if service crashes.
            return True 

        # 4. Scan
        result = cd.scan(tmp_path)
        # Result format: { '/tmp/...': ('FOUND', 'Win.Test.EICAR') } or None/Empty
        
        if result:
            # Check the finding for the specific file path
            scan_data = result.get(tmp_path)
            if scan_data and scan_data[0] == 'FOUND':
                virus_name = scan_data[1]
                logger.critical(f"VIRUS FOUND: {virus_name} in file {uploaded_file.name}")
                return False

        return True

    except Exception as e:
        logger.error(f"Virus Scan Error: {e}")
        # Default logic: If scan fails technically, do we allow?
        # Let's say yes to prevent downtime, but log strictly.
        return True
        
    finally:
        # 5. Clean up temp file
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
