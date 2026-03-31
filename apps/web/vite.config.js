import { defineConfig } from "vite";

const apiTarget = process.env.VITE_API_URL || "http://localhost:8000";
const brokerTarget = process.env.VITE_BROKER_URL || "http://localhost:8080";

export default defineConfig({
	server: {
		port: 5173,
		proxy: {
			"/api": apiTarget,
			"/broker": {
				target: brokerTarget,
				changeOrigin: true,
				rewrite: (path) => path.replace(/^\/broker/, "")
			}
		}
	}
});
