from fastapi import FastAPI

app = FastAPI(
    title="AI Logistics API",
    version="0.1.0",
    description="Fleet cost intelligence and logistics operations API.",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "logistics-api"}


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": "AI Logistics API",
        "version": "0.1.0",
        "status": "development",
    }
