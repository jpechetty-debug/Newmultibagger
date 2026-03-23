import json
import os
import datetime
import hashlib

class ScanLogger:
    def __init__(self, log_dir="logs"):
        self.log_dir = log_dir
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
            
    def _generate_version_hash(self):
        """Generates a hash of key logic files to ensure model consistency."""
        hasher = hashlib.md5()
        files_to_hash = [
            'modules/scoring.py',
            'modules/technicals.py',
            'modules/fundamentals.py'
        ]
        
        for file_path in files_to_hash:
            if os.path.exists(file_path):
                with open(file_path, 'rb') as f:
                    buf = f.read()
                    hasher.update(buf)
            else:
                hasher.update(b'MISSING')
                
        return hasher.hexdigest()[:8]

    def log_scan(self, universe_size, results_summary, config_snapshot=None):
        """
        Logs the details of a scan to a JSON file.
        
        Args:
            universe_size (int): Number of stocks scanned.
            results_summary (dict): High-level stats (e.g., number of elite picks).
            config_snapshot (dict): Key configuration parameters used.
        """
        timestamp = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        file_timestamp = datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S_%f")
        version_hash = self._generate_version_hash()
        
        log_entry = {
            "timestamp": timestamp,
            "version_hash": version_hash,
            "universe_size": universe_size,
            "config_snapshot": config_snapshot or {},
            "results_summary": results_summary
        }
        
        filename = f"scan_{file_timestamp}_{version_hash}.json"
        filepath = os.path.join(self.log_dir, filename)
        
        with open(filepath, 'w') as f:
            json.dump(log_entry, f, indent=4)
            
        print(f"Audit log saved: {filepath}")
        return filepath

