"""Entry point — start the Citi Bike Pass Optimizer."""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        app_dir="/Users/viraatchaudhary/Desktop/Distributed_Systems/HW7/bike_optimizer",
        host="0.0.0.0",
        port=8001,
        reload=True,
    )
