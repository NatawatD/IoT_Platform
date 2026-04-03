/**
 * Dashboard Page
 */

import React, { useEffect, useState } from 'react';
import { Row, Col, Card, Select, DatePicker, Spin } from 'antd';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { telemetryAPI, groupAPI, deviceAPI } from '../api';

const { RangePicker } = DatePicker;

function DashboardPage() {
  const [groups, setGroups] = useState([]);
  const [devices, setDevices] = useState([]);
  const [selectedGroup, setSelectedGroup] = useState(null);
  const [selectedDevice, setSelectedDevice] = useState(null);
  const [telemetry, setTelemetry] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    loadGroups();
  }, []);

  const loadGroups = async () => {
    try {
      const response = await groupAPI.list();
      setGroups(response.data || []);
    } catch (err) {
      setGroups([]);
    }
  };

  const loadDevices = async (groupId) => {
    try {
      const response = await deviceAPI.list(groupId);
      setDevices(response.data || []);
    } catch (err) {
      setDevices([]);
    }
  };

  const loadTelemetry = async (groupId, deviceId) => {
    setLoading(true);
    try {
      const response = await telemetryAPI.getHistory(groupId, deviceId, 'temperature');
      setTelemetry(response.data?.data || []);
    } catch (err) {
      setTelemetry([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={8}>
          <Select
            style={{ width: '100%' }}
            placeholder="Select Group"
            onChange={(value) => {
              setSelectedGroup(value);
              loadDevices(value);
            }}
          >
            {groups.map((g) => (
              <Select.Option key={g.group_id} value={g.group_id}>
                {g.name}
              </Select.Option>
            ))}
          </Select>
        </Col>
        <Col span={8}>
          <Select
            style={{ width: '100%' }}
            placeholder="Select Device"
            onChange={(value) => {
              setSelectedDevice(value);
              if (selectedGroup) loadTelemetry(selectedGroup, value);
            }}
          >
            {devices.map((d) => (
              <Select.Option key={d.device_id} value={d.device_id}>
                {d.name}
              </Select.Option>
            ))}
          </Select>
        </Col>
        <Col span={8}>
          <RangePicker style={{ width: '100%' }} />
        </Col>
      </Row>

      <Row gutter={16}>
        <Col span={24}>
          <Card title="Temperature (24h)" className="dashboard-card">
            {loading ? (
              <Spin />
            ) : (
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={telemetry}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="timestamp" />
                  <YAxis />
                  <Tooltip />
                  <Line type="monotone" dataKey="value" stroke="#1890ff" />
                </LineChart>
              </ResponsiveContainer>
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
}

export default DashboardPage;
