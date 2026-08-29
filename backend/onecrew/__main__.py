from __future__ import annotations

import uvicorn

from onecrew import config

if __name__ == "__main__":
    uvicorn.run(
        "onecrew.api:app",
        host=config.HOST,
        port=config.PORT,
        reload=False,
    )
