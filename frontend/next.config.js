/** @type {import('next').NextConfig} */
// 前后台同站部署（修正版规格 v2 §2）：生产环境用 rewrites 把 /api/* 代理到 FastAPI，
// 前台和后台同域名；本地开发时后端在 :8000，前端在 :3000。
const API_URL = process.env.API_URL || "http://localhost:8000";

const nextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
};

module.exports = nextConfig;
