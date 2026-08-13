<?php

if (! defined('ABSPATH')) {
    exit;
}

class LSOS_Auth
{
    private const MAX_CLOCK_SKEW_SECONDS = 300;

    public function authorize_request(WP_REST_Request $request)
    {
        $token = $this->configured_token();
        $secret = $this->configured_secret();

        if ($token === '' || $secret === '') {
            return new WP_Error('lsos_auth_not_configured', 'LSOS execution plugin credentials are not configured.', array('status' => 503));
        }

        $auth_header = (string) $request->get_header('authorization');
        if (! preg_match('/Bearer\s+(.+)/i', $auth_header, $matches)) {
            return new WP_Error('lsos_missing_bearer', 'Missing bearer token.', array('status' => 401));
        }

        $provided_token = trim((string) $matches[1]);
        if (! hash_equals($token, $provided_token)) {
            return new WP_Error('lsos_invalid_bearer', 'Invalid bearer token.', array('status' => 401));
        }

        $timestamp = (string) $request->get_header('x-lsos-timestamp');
        $nonce = trim((string) $request->get_header('x-lsos-nonce'));
        $signature = (string) $request->get_header('x-lsos-signature');
        if ($timestamp === '' || $nonce === '' || $signature === '') {
            return new WP_Error('lsos_missing_signature_headers', 'Missing timestamp, nonce, or signature header.', array('status' => 401));
        }
        if (! preg_match('/^[A-Za-z0-9_-]{20,128}$/', $nonce)) {
            return new WP_Error('lsos_invalid_nonce', 'Invalid request nonce.', array('status' => 401));
        }

        $timestamp_epoch = strtotime($timestamp);
        if ($timestamp_epoch === false || abs(time() - $timestamp_epoch) > self::MAX_CLOCK_SKEW_SECONDS) {
            return new WP_Error('lsos_expired_signature', 'Timestamp is outside the accepted replay window.', array('status' => 401));
        }

        $expected = hash_hmac('sha256', $timestamp . '.' . $nonce . '.' . $request->get_body(), $secret);
        if (! hash_equals($expected, $signature)) {
            return new WP_Error('lsos_invalid_signature', 'Invalid request signature.', array('status' => 401));
        }
        if (! LSOS_Audit_Store::claim_request_nonce($provided_token . ':' . $nonce, time() + self::MAX_CLOCK_SKEW_SECONDS)) {
            return new WP_Error('lsos_replayed_request', 'This signed request was already used.', array('status' => 409));
        }

        return true;
    }

    private function configured_token(): string
    {
        if ((string) get_option('lsos_execution_plugin_disconnected', '') === '1') {
            return '';
        }
        $saved = trim((string) get_option('lsos_execution_plugin_token', ''));
        if ($saved !== '') {
            return $saved;
        }
        return defined('LSOS_EXECUTION_PLUGIN_TOKEN')
            ? trim((string) LSOS_EXECUTION_PLUGIN_TOKEN)
            : '';
    }

    private function configured_secret(): string
    {
        if ((string) get_option('lsos_execution_plugin_disconnected', '') === '1') {
            return '';
        }
        $saved = trim((string) get_option('lsos_execution_plugin_shared_secret', ''));
        if ($saved !== '') {
            return $saved;
        }
        return defined('LSOS_EXECUTION_PLUGIN_SHARED_SECRET')
            ? trim((string) LSOS_EXECUTION_PLUGIN_SHARED_SECRET)
            : '';
    }
}
