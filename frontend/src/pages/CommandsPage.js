/**
 * Commands Page
 */

import React, { useEffect, useState } from 'react';
import { Form, Select, Input, Button, message } from 'antd';
import { groupAPI, deviceAPI, commandAPI } from '../api';

function CommandsPage() {
  const [groups, setGroups] = useState([]);
  const [devices, setDevices] = useState([]);
  const [selectedGroup, setSelectedGroup] = useState(null);

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

  const handleSend = async (values) => {
    if (!selectedGroup) {
      message.error('Select a group first');
      return;
    }

    try {
      await commandAPI.send(selectedGroup, values.device_id, values.command, { payload: values.payload });
      message.success('Command sent');
    } catch (err) {
      message.error('Failed to send command');
    }
  };

  return (
    <div>
      <Form layout="vertical" onFinish={handleSend}>
        <Form.Item label="Group" required>
          <Select
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
        </Form.Item>

        <Form.Item
          label="Device"
          name="device_id"
          rules={[{ required: true, message: 'Select a device' }]}
        >
          <Select placeholder="Select Device">
            {devices.map((d) => (
              <Select.Option key={d.device_id} value={d.device_id}>
                {d.name}
              </Select.Option>
            ))}
          </Select>
        </Form.Item>

        <Form.Item
          label="Command"
          name="command"
          rules={[{ required: true, message: 'Enter command' }]}
        >
          <Input placeholder="e.g. reboot, set_interval" />
        </Form.Item>

        <Form.Item label="Payload" name="payload">
          <Input.TextArea rows={4} placeholder='{"interval": 60}' />
        </Form.Item>

        <Form.Item>
          <Button type="primary" htmlType="submit">
            Send Command
          </Button>
        </Form.Item>
      </Form>
    </div>
  );
}

export default CommandsPage;
