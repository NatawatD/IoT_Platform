/**
 * Devices Page
 */

import React, { useEffect, useState } from 'react';
import { Table, Button, Modal, Form, Input, Select, message } from 'antd';
import { deviceAPI, groupAPI } from '../api';

function DevicesPage() {
  const [devices, setDevices] = useState([]);
  const [groups, setGroups] = useState([]);
  const [selectedGroup, setSelectedGroup] = useState(null);
  const [loading, setLoading] = useState(false);
  const [visible, setVisible] = useState(false);
  const [form] = Form.useForm();

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
    setLoading(true);
    try {
      const response = await deviceAPI.list(groupId);
      setDevices(response.data || []);
    } catch (err) {
      setDevices([]);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async (values) => {
    if (!selectedGroup) {
      message.error('Please select a group first');
      return;
    }

    try {
      await deviceAPI.create(selectedGroup, values.name, values.device_type);
      message.success('Device created');
      setVisible(false);
      form.resetFields();
      loadDevices(selectedGroup);
    } catch (err) {
      message.error('Failed to create device');
    }
  };

  const columns = [
    { title: 'Device ID', dataIndex: 'device_id', key: 'device_id' },
    { title: 'Name', dataIndex: 'name', key: 'name' },
    { title: 'Type', dataIndex: 'device_type', key: 'device_type' },
    { title: 'Status', dataIndex: 'status', key: 'status' },
  ];

  return (
    <div>
      <Select
        style={{ width: 240, marginBottom: 16 }}
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

      <Button type="primary" onClick={() => setVisible(true)} style={{ marginBottom: 16, marginLeft: 16 }}>
        Create Device
      </Button>

      <Table columns={columns} dataSource={devices} rowKey="device_id" loading={loading} />

      <Modal
        title="Create Device"
        open={visible}
        onCancel={() => setVisible(false)}
        onOk={() => form.submit()}
      >
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item
            label="Device Name"
            name="name"
            rules={[{ required: true, message: 'Please enter device name' }]}
          >
            <Input />
          </Form.Item>

          <Form.Item label="Device Type" name="device_type" initialValue="weather_station">
            <Select>
              <Select.Option value="weather_station">Weather Station</Select.Option>
              <Select.Option value="environment">Environment Sensor</Select.Option>
              <Select.Option value="custom">Custom</Select.Option>
            </Select>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

export default DevicesPage;
