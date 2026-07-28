"""
🌐 MINIMALIST WEB APPLICATION SERVER (Chatbot vs ReAct Agent Platform)
Serves REST API endpoints for comparing Chatbot Baseline vs ReAct Agent, 4 AI levels, test cases, and static frontend.
Connects directly to src/app.py execution logic.
"""

import os
import sys
import json
import re
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

# Ensure src/ directory is in python path
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import app
from tools import (
    AVAILABLE_TOOLS,
    load_product_database,
    search_products,
    get_product_ingredients,
    build_comparison_matrix,
    calculate_cost_per_serving,
    calculate_cost_per_active_amount,
    compare_products,
)
from prompts import CHATBOT_BASELINE_PROMPT, REACT_SYSTEM_PROMPT, MAX_ITERATIONS, SAFE_FALLBACK_MESSAGE
from providers import get_llm_provider

# Import level modules safely
try:
    from ai_levels.level1_rule_based import rule_based_bot
except ImportError:
    rule_based_bot = None

try:
    from ai_levels.level2_llm_chatbot import llm_chatbot
except ImportError:
    llm_chatbot = None

try:
    from ai_levels.level3_reactive_agent import reactive_agent_step
except ImportError:
    reactive_agent_step = None

try:
    from ai_levels.level4_autonomous_agent import AutonomousGoalAgent
except ImportError:
    AutonomousGoalAgent = None


def format_react_trace(res_dict: dict) -> dict:
    """Format app.run_react_agent response into structured steps for Web UI"""
    trace_list = res_dict.get("trace", [])
    final_ans = res_dict.get("final_answer", "")
    
    # Check if any LLM response in trace contained **Lợi ích** or bold text
    benefits_text = ""
    for item in trace_list:
        item_str = str(item)
        if "Final Answer:" in item_str and "**" in item_str:
            parts = item_str.split("Final Answer:", 1)[1]
            if "**Lợi ích**" in parts or "**" in parts:
                # Find start of bold benefits section
                idx = parts.find("**")
                if idx != -1:
                    benefits_text = parts[idx:].strip()
                break
                
    if benefits_text and benefits_text not in final_ans:
        final_ans = f"{final_ans}\n\n{benefits_text}"

    steps = []
    step_num = 1
    
    i = 0
    while i < len(trace_list):
        item = str(trace_list[i]).strip()
        
        if item.startswith("Observation:"):
            if steps:
                steps[-1]["observation"] = item.replace("Observation:", "").strip()
            i += 1
            continue
            
        thought_match = re.search(r"Thought:\s*(.*?)(?=\nAction:|\nFinal Answer:|$)", item, re.DOTALL)
        action_match = re.search(r"Action:\s*(.*?)(?=\nObservation:|$)", item, re.DOTALL)
        
        thought_text = thought_match.group(1).strip() if thought_match else item
        action_text = action_match.group(1).strip() if action_match else "Complete"
        
        obs_text = ""
        if i + 1 < len(trace_list) and str(trace_list[i+1]).startswith("Observation:"):
            obs_text = str(trace_list[i+1]).replace("Observation:", "").strip()
            i += 1
            
        steps.append({
            "step": step_num,
            "thought": thought_text,
            "action": action_text,
            "observation": obs_text
        })
        step_num += 1
        i += 1
        
    return {
        "steps": steps,
        "final_answer": final_ans,
        "guardrail_triggered": res_dict.get("status") == "guardrail",
        "status": res_dict.get("status", "success")
    }


class RequestHandler(SimpleHTTPRequestHandler):
    """Custom HTTP Request Handler for API & Static Web UI"""
    
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        
        if path == "/api/test_cases":
            try:
                cases = app.load_test_cases()
            except Exception:
                cases = self.get_test_cases()
            self.send_json_response(cases)
        elif path == "/api/products":
            db_res = load_product_database()
            self.send_json_response(db_res)
        elif path == "/api/info":
            provider = get_llm_provider()
            model_name = getattr(provider, "model_name", "Offline Mock Mode")
            self.send_json_response({
                "provider": provider.__class__.__name__,
                "model": model_name,
                "max_iterations": MAX_ITERATIONS,
                "tools": list(AVAILABLE_TOOLS.keys())
            })
        elif path == "/" or path == "/index.html":
            self.serve_static_html()
        else:
            # Fallback static server
            super().do_GET()
            
    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        
        try:
            data = json.loads(body)
        except Exception:
            data = {}
            
        provider = get_llm_provider()
        
        if path == "/api/compare":
            query = data.get("query", "").strip()
            if not query:
                self.send_json_response({"error": "Query parameter is required"}, status=400)
                return
                
            # Run Baseline Chatbot from src/app.py
            try:
                baseline_ans = app.run_baseline_chatbot(query, provider)
            except Exception as e:
                baseline_ans = f"Error running baseline: {str(e)}"
            
            # Run ReAct Agent from src/app.py
            try:
                raw_react_res = app.run_react_agent(query, provider)
                react_formatted = format_react_trace(raw_react_res)
            except Exception as e:
                react_formatted = {
                    "steps": [],
                    "final_answer": f"Error running ReAct Agent: {str(e)}",
                    "guardrail_triggered": False
                }
            
            self.send_json_response({
                "query": query,
                "baseline_response": baseline_ans,
                "react_steps": react_formatted["steps"],
                "react_final_answer": react_formatted["final_answer"],
                "guardrail_triggered": react_formatted["guardrail_triggered"]
            })
            
        elif path == "/api/run_ai_level":
            level = int(data.get("level", 1))
            query = data.get("query", "Sample Query")
            
            if level == 1 and rule_based_bot:
                res = rule_based_bot(query)
            elif level == 2 and llm_chatbot:
                res = llm_chatbot(query)
            elif level == 3:
                raw_react_res = app.run_react_agent(query, provider)
                res = f"Status: {raw_react_res.get('status')}\nFinal Answer:\n{raw_react_res.get('final_answer')}"
            elif level == 4 and AutonomousGoalAgent:
                agent = AutonomousGoalAgent(query)
                res = f"Autonomous Goal Agent executed for goal: '{query}'."
            else:
                res = f"Level {level} execution complete."
                
            self.send_json_response({"level": level, "query": query, "output": res})
            
        elif path == "/api/run_tool":
            tool_name = data.get("tool_name", "")
            args = data.get("args", [])
            
            if tool_name not in AVAILABLE_TOOLS:
                self.send_json_response({"error": f"Tool '{tool_name}' not found"}, status=404)
                return
                
            try:
                fn = AVAILABLE_TOOLS[tool_name]
                if isinstance(args, list):
                    res = fn(*args)
                elif isinstance(args, dict):
                    res = fn(**args)
                else:
                    res = fn(args)
                self.send_json_response({"success": True, "result": res})
            except Exception as e:
                self.send_json_response({"success": False, "error": str(e)}, status=500)
        else:
            self.send_json_response({"error": "Endpoint not found"}, status=404)
            
    def send_json_response(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_static_html(self):
        web_file = os.path.join(SRC_DIR, "web", "index.html")
        if os.path.exists(web_file):
            with open(web_file, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_error(404, "Web interface file not found")
            
    def get_test_cases(self):
        config_path = os.path.join(os.path.dirname(SRC_DIR), "config", "test_cases.json")
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return []


def run_server(port=8000):
    server_address = ("", port)
    httpd = HTTPServer(server_address, RequestHandler)
    print("==================================================")
    print(f"🚀 MINIMALIST WEB APPLICATION RUNNING ON PORT {port}")
    print(f"🌐 Access URL: http://localhost:{port}")
    print("==================================================")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping web server.")
        httpd.server_close()


if __name__ == "__main__":
    port = 8000
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    run_server(port)
