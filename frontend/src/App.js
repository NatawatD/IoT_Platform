/**
 * App.js - Main React Application
 */

import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { Layout, Menu, Dropdown, Avatar, message } from 'antd';
import { LogoutOutlined, DashboardOutlined, AppstoreOutlined, ControlOutlined } from '@ant-design/icons';
import './App.css';

// Pages
import LoginPage from './pages/LoginPage';
import DashboardPage from './pages/DashboardPage';
import GroupsPage from './pages/GroupsPage';
import DevicesPage from './pages/DevicesPage';
import CommandsPage from './pages/CommandsPage';

const { Header, Sider, Content } = Layout;

function PrivateRoute({ children }) {
  const token = localStorage.getItem('access_token');
  return token ? children : <Navigate to="/login" />;
}

function App() {
  const [collapsed, setCollapsed] = useState(false);
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Check if user is logged in
    const token = localStorage.getItem('access_token');
    const userEmail = localStorage.getItem('user_email');
    
    if (token && userEmail) {
      setUser({ email: userEmail });
    }
    
    setLoading(false);
  }, []);

  const handleLogout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user_email');
    setUser(null);
    message.success('Logged out successfully');
    window.location.href = '/login';
  };

  const userMenu = (
    <Menu>
      <Menu.Item key="logout" icon={<LogoutOutlined />} onClick={handleLogout}>
        Logout
      </Menu.Item>
    </Menu>
  );

  if (loading) {
    return <div>Loading...</div>;
  }

  if (!user) {
    return (
      <Router>
        <Routes>
          <Route path="/login" element={<LoginPage onLoginSuccess={(email) => {
            setUser({ email });
          }} />} />
          <Route path="*" element={<Navigate to="/login" />} />
        </Routes>
      </Router>
    );
  }

  return (
    <Router>
      <Layout style={{ minHeight: '100vh' }}>
        <Sider trigger={null} collapsible collapsed={collapsed}>
          <div className="logo">
            <h2>{collapsed ? 'IoT' : 'IoT Platform'}</h2>
          </div>
          <Menu theme="dark" mode="inline" defaultSelectedKeys={['dashboard']}>
            <Menu.Item key="dashboard" icon={<DashboardOutlined />}>
              <a href="/dashboard">Dashboard</a>
            </Menu.Item>
            <Menu.Item key="groups" icon={<AppstoreOutlined />}>
              <a href="/groups">Groups</a>
            </Menu.Item>
            <Menu.Item key="devices" icon={<ControlOutlined />}>
              <a href="/devices">Devices</a>
            </Menu.Item>
            <Menu.Item key="commands" icon={<LogoutOutlined />}>
              <a href="/commands">Commands</a>
            </Menu.Item>
          </Menu>
        </Sider>
        <Layout className="site-layout">
          <Header style={{ background: '#fff', padding: '0 16px', boxShadow: '0 2px 8px rgba(0,0,0,0.1)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <button onClick={() => setCollapsed(!collapsed)} style={{ background: 'none', border: 'none', fontSize: '16px' }}>
                {collapsed ? '≡' : '≡'}
              </button>
              <Dropdown overlay={userMenu} trigger={['click']}>
                <div style={{ display: 'flex', alignItems: 'center', cursor: 'pointer' }}>
                    <Avatar size="large" style={{ marginRight: '8px', backgroundColor: '#87d068' }}>
                    {user.email?.charAt(0)?.toUpperCase()}
                  </Avatar>
                  <span>{user.email}</span>
                </div>
              </Dropdown>
            </div>
          </Header>
          <Content style={{ margin: '16px' }}>
            <Routes>
              <Route path="/dashboard" element={<PrivateRoute><DashboardPage /></PrivateRoute>} />
              <Route path="/groups" element={<PrivateRoute><GroupsPage /></PrivateRoute>} />
              <Route path="/devices" element={<PrivateRoute><DevicesPage /></PrivateRoute>} />
              <Route path="/commands" element={<PrivateRoute><CommandsPage /></PrivateRoute>} />
              <Route path="*" element={<Navigate to="/dashboard" />} />
            </Routes>
          </Content>
        </Layout>
      </Layout>
    </Router>
  );
}

export default App;
