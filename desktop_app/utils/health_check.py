import requests
import time

def check_server_health(url, timeout=1, retries=3, interval=0.5):
    """
    Check if the server is healthy by polling the given URL.
    Returns True if healthy, False otherwise.
    """
    for _ in range(retries):
        try:
            response = requests.get(url, timeout=timeout)
            if response.status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(interval)
    return False
