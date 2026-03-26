# PostgreSQL Schema Init — IoT Platform
# Run this script to initialize the database schema.
# Usage: psql -U iot_user -d iot_platform -f init.sql

-- ============================================================
-- Users
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(256) UNIQUE NOT NULL,
    password_hash VARCHAR(256) NOT NULL,
    full_name VARCHAR(256),
    role VARCHAR(32) DEFAULT 'user',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- Groups (project isolation boundary)
-- ============================================================
CREATE TABLE IF NOT EXISTS groups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id VARCHAR(64) UNIQUE NOT NULL,
    name VARCHAR(256) NOT NULL,
    owner_id UUID NOT NULL REFERENCES users(id),
    tier VARCHAR(32) DEFAULT 'free',
    max_devices INT DEFAULT 10,
    default_ttl_days INT DEFAULT 30,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- Devices
-- ============================================================
CREATE TABLE IF NOT EXISTS devices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id VARCHAR(128) NOT NULL,
    group_id UUID NOT NULL REFERENCES groups(id),
    name VARCHAR(256),
    device_type VARCHAR(64) DEFAULT 'weather_station',
    status VARCHAR(32) DEFAULT 'offline',
    last_seen TIMESTAMP,
    metadata JSONB DEFAULT '{}',
    ttl_days INT DEFAULT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(device_id, group_id)
);

-- ============================================================
-- Device Credentials (NETPIE-style 3-part)
-- ============================================================
CREATE TABLE IF NOT EXISTS device_credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id UUID NOT NULL REFERENCES devices(id),
    group_id UUID NOT NULL REFERENCES groups(id),
    client_id VARCHAR(128) UNIQUE NOT NULL,
    token_hash VARCHAR(128) NOT NULL,
    secret_hash VARCHAR(128) NOT NULL,
    is_active BOOLEAN DEFAULT true,
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- User Tokens (JWT refresh tokens)
-- ============================================================
CREATE TABLE IF NOT EXISTS user_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    refresh_token_hash VARCHAR(256) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    is_revoked BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- Indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_groups_owner ON groups(owner_id);
CREATE INDEX IF NOT EXISTS idx_devices_group ON devices(group_id);
CREATE INDEX IF NOT EXISTS idx_credentials_client ON device_credentials(client_id);
CREATE INDEX IF NOT EXISTS idx_user_tokens_user ON user_tokens(user_id);
