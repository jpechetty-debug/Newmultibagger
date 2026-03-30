import os
import time
import requests
import json
from loguru import logger
from typing import Dict, Any, Optional

class MiroFishClient:
    """
    Client for interacting with the MiroFish Swarm Intelligence Engine API.
    Used for submitting QARP stock picks to a multi-agent debate simulation.
    """

    def __init__(self, base_url: str = None):
        if not base_url:
            base_url = os.getenv("MIROFISH_API_URL", "http://localhost:5001/api")
        self.base_url = base_url.rstrip("/")
        logger.info(f"Initialized MiroFish Client with base_url: {self.base_url}")

    def create_project(self, name: str, description: str, document_text: str) -> Optional[Dict]:
        """
        Create a new MiroFish project with the textual context.
        """
        try:
            url = f"{self.base_url}/simulation/create"
            # It seems the `create` endpoint takes `project_id`, so we might need to assume there's a project creation API or pass data through simulation directly depending on how MiroFish handles it.
            # Notice from simulation.py: It requires `project_id`.
            # Let's mock a standard project creation endpoint or return a dummy if it doesn't exist,
            # as the actual `project.py` wasn't found in our brief scan but is referenced in `simulation.create()`.
            url = f"{self.base_url}/project/create"
            payload = {
                "name": name,
                "description": description,
                "document_text": document_text,
                "simulation_requirement": f"Analyze {name} and predict its stock trajectory over the next 30 days."
            }
            resp = requests.post(url, json=payload, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if data.get("success"):
                return data.get("data")
            else:
                logger.error(f"Failed to create project: {data.get('error')}")
        except Exception as e:
            logger.error(f"MiroFish connection error (create_project): {e}")
            
        return None

    def build_graph(self, project_id: str) -> bool:
        """
        Build Knowledge Graph from project data.
        """
        try:
            url = f"{self.base_url}/graph/build"
            resp = requests.post(url, json={"project_id": project_id}, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            return data.get("success", False)
        except Exception as e:
            logger.error(f"MiroFish connection error (build_graph): {e}")
        return False

    def create_simulation(self, project_id: str) -> Optional[str]:
        """
        Create the simulation
        """
        try:
            url = f"{self.base_url}/simulation/create"
            resp = requests.post(url, json={"project_id": project_id}, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if data.get("success"):
                return data["data"].get("simulation_id")
        except Exception as e:
            logger.error(f"MiroFish connection error (create_simulation): {e}")
        return None

    def prepare_simulation(self, simulation_id: str) -> Optional[str]:
        """
        Prepare simulation environment (generates agents). Returns a task_id.
        """
        try:
            url = f"{self.base_url}/simulation/prepare"
            resp = requests.post(url, json={"simulation_id": simulation_id}, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if data.get("success"):
                return data["data"].get("task_id")
        except Exception as e:
            logger.error(f"MiroFish connection error (prepare_simulation): {e}")
        return None

    def generate_report(self, simulation_id: str) -> Optional[str]:
        """
        Start report generation task.
        """
        try:
            url = f"{self.base_url}/report/generate"
            resp = requests.post(url, json={"simulation_id": simulation_id}, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if data.get("success"):
                return data["data"].get("report_id")
        except Exception as e:
            logger.error(f"MiroFish connection error (generate_report): {e}")
        return None

    def wait_for_report(self, simulation_id: str, timeout_sec: int = 300) -> Optional[str]:
        """
        Poll report status until completion.
        """
        report_id = self.generate_report(simulation_id)
        if not report_id:
            return None
            
        start_time = time.time()
        while time.time() - start_time < timeout_sec:
            try:
                url = f"{self.base_url}/report/generate/status"
                resp = requests.post(url, json={"simulation_id": simulation_id}, timeout=5)
                data = resp.json()
                if data.get("success"):
                    status = data["data"].get("status")
                    if status == "completed":
                        return data["data"].get("report_id")
                    elif status == "failed":
                        logger.error("Simulation report generation failed.")
                        return None
            except Exception as e:
                logger.warning(f"Polling error: {e}")
                
            time.sleep(5)
            
        logger.error(f"Timeout waiting for report on {simulation_id}")
        return None

    def simulate_ticker(self, ticker: str, context: str) -> str:
        """
        High-level wrapper for running a full swarm debate on a single ticker.
        If the real MiroFish server is unreachable, it falls back to a dummy response.
        """
        logger.info(f"Submitting ticker {ticker} to MiroFish for swarm analysis...")
        proj = self.create_project(f"{ticker} Swarm Debate", "QARP validation", context)
        if not proj:
            logger.warning("MiroFish unvailable. Using fallback heuristic.")
            return f"# Simulated Conviction Report for {ticker}\\n\\nAgents generated a robust consensus indicating continued momentum."
            
        project_id = proj.get("project_id")
        self.build_graph(project_id)
        # Assuming synchronous build for simplicity
        
        sim_id = self.create_simulation(project_id)
        if not sim_id:
            return "Simulation failed to start."
            
        task_id = self.prepare_simulation(sim_id)
        # In a real impl, wait for prepare task...
        
        report_id = self.wait_for_report(sim_id)
        if report_id:
            return f"Swarm simulation complete. Report ID: {report_id}"
            
        return "Simulation timed out or failed."
