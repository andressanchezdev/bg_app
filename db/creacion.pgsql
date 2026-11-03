-- =============================================================================
-- ESQUEMA DE BASE DE DATOS: IA BACKGROUND REMOVER & WEBP OPTIMIZER
-- Motor: PostgreSQL 12+ (Compatible con pgAdmin 4)
-- =============================================================================

-- 1. Tabla de Parámetros y Configuraciones de la Aplicación
CREATE TABLE IF NOT EXISTS app_settings (
    key VARCHAR(100) PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Tabla de Lotes / Sesiones de Procesamiento Masivo
CREATE TABLE IF NOT EXISTS batches (
    id SERIAL PRIMARY KEY,
    input_path TEXT NOT NULL,
    total_images INTEGER DEFAULT 0,
    processed_images INTEGER DEFAULT 0,
    status VARCHAR(50) DEFAULT 'pending',
    destination_type VARCHAR(50) DEFAULT 'local',
    destination_path TEXT,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP
);

-- 3. Tabla de Imágenes Individuales Procesadas
CREATE TABLE IF NOT EXISTS images (
    id SERIAL PRIMARY KEY,
    batch_id INTEGER REFERENCES batches(id) ON DELETE CASCADE,
    filename VARCHAR(255) NOT NULL,
    folder_name VARCHAR(255),
    relative_path TEXT,
    original_path TEXT NOT NULL,
    processed_path TEXT,
    original_size BIGINT DEFAULT 0,
    processed_size BIGINT DEFAULT 0,
    format VARCHAR(20),
    status VARCHAR(50) DEFAULT 'pending',
    cloud_url TEXT,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP
);

-- 4. Índices para Optimización de Búsqueda y Consultas Rápidas
CREATE INDEX IF NOT EXISTS idx_images_batch_id ON images(batch_id);
CREATE INDEX IF NOT EXISTS idx_images_status ON images(status);
CREATE INDEX IF NOT EXISTS idx_images_original_path ON images(original_path);
CREATE INDEX IF NOT EXISTS idx_batches_status ON batches(status);