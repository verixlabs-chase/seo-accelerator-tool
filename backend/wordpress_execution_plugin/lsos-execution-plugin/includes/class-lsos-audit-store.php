<?php

if (! defined('ABSPATH')) {
    exit;
}

class LSOS_Audit_Store
{
    private const SCHEMA_VERSION = '1.1.0';

    public static function maybe_upgrade(): void
    {
        if ((string) get_option('lsos_execution_schema_version', '') === self::SCHEMA_VERSION) {
            return;
        }
        self::install();
    }

    public static function install(): void
    {
        global $wpdb;
        require_once ABSPATH . 'wp-admin/includes/upgrade.php';

        $table = self::table_name();
        $charset = $wpdb->get_charset_collate();
        $sql = "CREATE TABLE {$table} (
            id bigint(20) unsigned NOT NULL AUTO_INCREMENT,
            mutation_id varchar(128) NOT NULL,
            execution_id varchar(128) NOT NULL,
            mutation_type varchar(64) NOT NULL,
            source_url text NULL,
            target_url text NOT NULL,
            status varchar(32) NOT NULL,
            before_state longtext NULL,
            after_state longtext NULL,
            rollback_payload longtext NULL,
            request_signature varchar(255) NULL,
            created_at datetime NOT NULL,
            rolled_back_at datetime NULL,
            PRIMARY KEY (id),
            UNIQUE KEY mutation_id (mutation_id)
        ) {$charset};";

        dbDelta($sql);

        $nonce_table = self::nonce_table_name();
        $nonce_sql = "CREATE TABLE {$nonce_table} (
            nonce_hash char(64) NOT NULL,
            expires_at datetime NOT NULL,
            created_at datetime NOT NULL,
            PRIMARY KEY (nonce_hash),
            KEY expires_at (expires_at)
        ) {$charset};";
        dbDelta($nonce_sql);
        update_option('lsos_execution_schema_version', self::SCHEMA_VERSION, false);
    }

    public static function table_name(): string
    {
        global $wpdb;
        return $wpdb->prefix . 'lsos_execution_audit';
    }

    public static function nonce_table_name(): string
    {
        global $wpdb;
        return $wpdb->prefix . 'lsos_request_nonces';
    }

    public static function claim_request_nonce(string $nonce, int $expires_at): bool
    {
        global $wpdb;
        $table = self::nonce_table_name();
        $now = current_time('mysql', true);
        $wpdb->query($wpdb->prepare('DELETE FROM ' . $table . ' WHERE expires_at < %s', $now));
        $inserted = $wpdb->query(
            $wpdb->prepare(
                'INSERT IGNORE INTO ' . $table . ' (nonce_hash, expires_at, created_at) VALUES (%s, %s, %s)',
                hash('sha256', $nonce),
                gmdate('Y-m-d H:i:s', $expires_at),
                $now
            )
        );
        return $inserted === 1;
    }

    public function get_mutation(string $mutation_id): ?array
    {
        global $wpdb;
        $row = $wpdb->get_row($wpdb->prepare('SELECT * FROM ' . self::table_name() . ' WHERE mutation_id = %s LIMIT 1', $mutation_id), ARRAY_A);
        if (! is_array($row)) {
            return null;
        }

        foreach (array('before_state', 'after_state', 'rollback_payload') as $key) {
            $decoded = json_decode((string) ($row[$key] ?? ''), true);
            $row[$key] = is_array($decoded) ? $decoded : array();
        }

        return $row;
    }

    public function record_mutation(array $record): void
    {
        global $wpdb;

        $wpdb->replace(
            self::table_name(),
            array(
                'mutation_id' => (string) ($record['mutation_id'] ?? ''),
                'execution_id' => (string) ($record['execution_id'] ?? ''),
                'mutation_type' => (string) ($record['mutation_type'] ?? ''),
                'source_url' => isset($record['source_url']) ? (string) $record['source_url'] : null,
                'target_url' => (string) ($record['target_url'] ?? ''),
                'status' => (string) ($record['status'] ?? 'applied'),
                'before_state' => wp_json_encode($record['before_state'] ?? array()),
                'after_state' => wp_json_encode($record['after_state'] ?? array()),
                'rollback_payload' => wp_json_encode($record['rollback_payload'] ?? array()),
                'request_signature' => isset($record['request_signature']) ? (string) $record['request_signature'] : null,
                'created_at' => current_time('mysql', true),
                'rolled_back_at' => null,
            ),
            array('%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s')
        );
    }

    public function mark_rolled_back(string $mutation_id, array $after_state): void
    {
        global $wpdb;

        $wpdb->update(
            self::table_name(),
            array(
                'status' => 'rolled_back',
                'after_state' => wp_json_encode($after_state),
                'rolled_back_at' => current_time('mysql', true),
            ),
            array('mutation_id' => $mutation_id),
            array('%s', '%s', '%s'),
            array('%s')
        );
    }
}
