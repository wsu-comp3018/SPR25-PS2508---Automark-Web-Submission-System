// Auto-detect environment
const isDevelopment = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
const isDocker = window.location.port === '3000'; // Nginx container

export const API_BASE_URL = isDevelopment && !isDocker 
  ? "http://127.0.0.1:8000/api/v1"  // Local development
  : "/api/v1";                       // Production/Docker (proxied by Nginx)
