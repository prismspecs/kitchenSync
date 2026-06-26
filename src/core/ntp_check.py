#!/usr/bin/env python3
"""
Utility for checking NTP synchronization status via chrony.
"""

import subprocess
import shutil
from typing import Dict, Any

def get_ntp_status() -> Dict[str, Any]:
    """
    Run `chronyc tracking` and parse the output to determine sync status.
    Returns a dictionary with status details.
    """
    status = {
        "synced": False,
        "stratum": 0,
        "offset": 0.0,
        "rms_offset": 0.0,
        "reference_id": "unknown",
        "error": None
    }
    
    chronyc_path = shutil.which("chronyc")
    if not chronyc_path:
        status["error"] = "chronyc binary not found"
        return status
        
    try:
        result = subprocess.run(
            [chronyc_path, "tracking"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode != 0:
            status["error"] = f"chronyc exited with code {result.returncode}: {result.stderr.strip()}"
            return status
            
        lines = result.stdout.splitlines()
        for line in lines:
            if ":" not in line:
                continue
            key, val = line.split(":", 1)
            key = key.strip()
            val = val.strip()
            
            if "Reference ID" in key:
                status["reference_id"] = val
            elif "Stratum" in key:
                try:
                    status["stratum"] = int(val)
                except ValueError:
                    pass
            elif "System time" in key:
                parts = val.split()
                if parts:
                    try:
                        offset = float(parts[0])
                        if "slow" in val:
                            offset = -offset
                        status["offset"] = offset
                    except ValueError:
                        pass
            elif "RMS offset" in key:
                parts = val.split()
                if parts:
                    try:
                        status["rms_offset"] = float(parts[0])
                    except ValueError:
                        pass
                        
        if status["stratum"] > 0 and "0.0.0.0" not in status["reference_id"] and "Not synchronised" not in status["reference_id"]:
            status["synced"] = True
            
    except subprocess.TimeoutExpired:
        status["error"] = "chronyc command timed out"
    except Exception as e:
        status["error"] = f"Failed to check NTP: {e}"
        
    return status
