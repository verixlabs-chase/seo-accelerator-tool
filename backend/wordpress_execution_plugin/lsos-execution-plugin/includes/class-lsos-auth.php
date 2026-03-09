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
        $signature = (string) $request->get_header('x-lsos-signature');
        if ($timestamp === '' || $signature === '') {
            return new WP_Error('lsos_missing_signature_headers', 'Missing timestamp or signature header.', array('status' => 401));
        }

        $timestamp_epoch = strtotime($timestamp);
        if ($timestamp_epoch === false || abs(time() - $timestamp_epoch) > self::MAX_CLOCK_SKEW_SECONDS) {
            return new WP_Error('lsos_expired_signature', 'Timestamp is outside the accepted replay window.', array('status' => 401));
        }

        $expected = hash_hmac('sha256', $timestamp . '.' . $request->get_body(), $secret);
        if (! hash_equals($expected, $signature)) {
            return new WP_Error('lsos_invalid_signature', 'Invalid request signature.', array('status' => 401));
        }

        return true;
    }

    private function configured_token(): string
    {
        if (defined('LSOS_EXECUTION_PLUGIN_TOKEN')) {
            return trim((string) LSOS_EXECUTION_PLUGIN_TOKEN);
        }

        return trim((string) get_option('lsos_execution_plugin_token', ''));
    }

    private function configured_secret(): string
    {
        if (defined('LSOS_EXECUTION_PLUGIN_SHARED_SECRET')) {
            return trim((string) LSOS_EXECUTION_PLUGIN_SHARED_SECRET);
        }

        return trim((string) get_option('lsos_execution_plugin_shared_secret', ''));
    }
}
