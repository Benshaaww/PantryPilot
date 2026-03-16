import sys

def check():
    print(f"Python: {sys.version}")
    
    modules = ["langchain", "langchain_openai", "langchain_community", "pydantic"]
    for m in modules:
        try:
            mod = __import__(m.replace("-", "_"))
            version = getattr(mod, "__version__", "Found")
            print(f"✅ {m:20} : {version}")
        except ImportError as e:
            print(f"❌ {m:20} : FAILED ({e})")

if __name__ == "__main__":
    check()
