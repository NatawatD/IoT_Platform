/**
 * API Service - Client for IoT Backend
 */

import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000/api/v1';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add token to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle 401 responses
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      // Try to refresh token
      const refreshToken = localStorage.getItem('refresh_token');
      if (refreshToken) {
        try {
          const response = await axios.post(`${API_BASE_URL}/auth/refresh`, {
            refresh_token: refreshToken,
          });
          localStorage.setItem('access_token', response.data.access_token);
          // Retry original request
          return api(error.config);
        } catch (err) {
          localStorage.removeItem('access_token');
          localStorage.removeItem('refresh_token');
          window.location.href = '/login';
        }
      }
    }
    return Promise.reject(error);
  }
);

// Auth endpoints
export const authAPI = {
  register: (email, password, fullName) =>
    api.post('/auth/register', { email, password, full_name: fullName }),
  login: (email, password) =>
    api.post('/auth/login', { email, password }),
  refresh: (refreshToken) =>
    api.post('/auth/refresh', { refresh_token: refreshToken }),
  logout: () =>
    api.post('/auth/logout'),
};

// Group endpoints
export const groupAPI = {
  list: () => api.get('/groups'),
  get: (groupId) => api.get(`/groups/${groupId}`),
  create: (name, tier = 'free') =>
    api.post('/groups', { name, tier }),
  update: (groupId, name, tier) =>
    api.put(`/groups/${groupId}`, { name, tier }),
  delete: (groupId) =>
    api.delete(`/groups/${groupId}`),
};

// Device endpoints
export const deviceAPI = {
  list: (groupId) => api.get(`/groups/${groupId}/devices`),
  get: (groupId, deviceId) =>
    api.get(`/groups/${groupId}/devices/${deviceId}`),
  create: (groupId, name, deviceType = 'weather_station') =>
    api.post(`/groups/${groupId}/devices`, { name, device_type: deviceType }),
  update: (groupId, deviceId, name, deviceType) =>
    api.put(`/groups/${groupId}/devices/${deviceId}`, { name, device_type: deviceType }),
  delete: (groupId, deviceId) =>
    api.delete(`/groups/${groupId}/devices/${deviceId}`),
};

// Credentials endpoints
export const credentialAPI = {
  generate: (groupId, deviceId) =>
    api.post(`/groups/${groupId}/devices/${deviceId}/credentials`),
  regenerate: (groupId, deviceId) =>
    api.post(`/groups/${groupId}/devices/${deviceId}/credentials/regenerate`),
};

// Telemetry endpoints
export const telemetryAPI = {
  getLatest: (groupId, deviceId) =>
    api.get(`/groups/${groupId}/devices/${deviceId}/telemetry`),
  getHistory: (groupId, deviceId, sensorType, fromTime, toTime) =>
    api.get(`/groups/${groupId}/telemetry/history`, {
      params: {
        device_id: deviceId,
        sensor_type: sensorType,
        from_time: fromTime,
        to_time: toTime,
      },
    }),
};

// Command endpoints
export const commandAPI = {
  send: (groupId, deviceId, command, parameters = {}) =>
    api.post(`/groups/${groupId}/devices/${deviceId}/commands`, {
      command,
      parameters,
    }),
};

// Dashboard endpoints
export const dashboardAPI = {
  list: (groupId) => api.get(`/groups/${groupId}/dashboards`),
  get: (groupId, dashboardId) =>
    api.get(`/groups/${groupId}/dashboards/${dashboardId}`),
  create: (groupId, name, widgets = []) =>
    api.post(`/groups/${groupId}/dashboards`, { name, widgets }),
  update: (groupId, dashboardId, name, widgets) =>
    api.put(`/groups/${groupId}/dashboards/${dashboardId}`, { name, widgets }),
  delete: (groupId, dashboardId) =>
    api.delete(`/groups/${groupId}/dashboards/${dashboardId}`),
};

export default api;
