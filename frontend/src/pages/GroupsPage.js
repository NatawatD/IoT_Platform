/**
 * Groups Page
 */

import React, { useEffect, useState } from 'react';
import { Table, Button, Modal, Form, Input, message } from 'antd';
import { groupAPI } from '../api';

function GroupsPage() {
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(false);
  const [visible, setVisible] = useState(false);
  const [form] = Form.useForm();

  useEffect(() => {
    loadGroups();
  }, []);

  const loadGroups = async () => {
    setLoading(true);
    try {
      const response = await groupAPI.list();
      setGroups(response.data || []);
    } catch (err) {
      setGroups([]);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async (values) => {
    try {
      await groupAPI.create(values.name, 'free');
      message.success('Group created');
      setVisible(false);
      form.resetFields();
      loadGroups();
    } catch (err) {
      message.error('Failed to create group');
    }
  };

  const columns = [
    { title: 'Group ID', dataIndex: 'group_id', key: 'group_id' },
    { title: 'Name', dataIndex: 'name', key: 'name' },
    { title: 'Tier', dataIndex: 'tier', key: 'tier' },
    { title: 'Max Devices', dataIndex: 'max_devices', key: 'max_devices' },
  ];

  return (
    <div>
      <Button type="primary" onClick={() => setVisible(true)} style={{ marginBottom: 16 }}>
        Create Group
      </Button>

      <Table columns={columns} dataSource={groups} rowKey="group_id" loading={loading} />

      <Modal
        title="Create Group"
        open={visible}
        onCancel={() => setVisible(false)}
        onOk={() => form.submit()}
      >
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item
            label="Group Name"
            name="name"
            rules={[{ required: true, message: 'Please enter group name' }]}
          >
            <Input />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

export default GroupsPage;
