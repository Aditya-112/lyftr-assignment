import os

import uvicorn


uvicorn.run("app.main:create_app", factory=True, host="0.0.0.0", port=int(os.getenv("PORT", "8000")), workers=1)
