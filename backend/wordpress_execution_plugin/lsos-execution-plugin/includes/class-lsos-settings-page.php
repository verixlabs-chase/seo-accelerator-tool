<?php

if (! defined('ABSPATH')) {
    exit;
}

class LSOS_Settings_Page
{
    public function register(): void
    {
        add_action('admin_menu', array($this, 'add_settings_page'));
        add_action('admin_post_lsos_pair_site', array($this, 'pair_site'));
        add_action('admin_post_lsos_disconnect_site', array($this, 'disconnect_site'));
    }

    public function add_settings_page(): void
    {
        add_options_page(
            'InsightOS',
            'InsightOS',
            'manage_options',
            'lsos-execution-plugin',
            array($this, 'render')
        );
    }

    public function render(): void
    {
        if (! current_user_can('manage_options')) {
            return;
        }

        $connected = $this->is_connected();
        $notice = sanitize_key((string) ($_GET['lsos_notice'] ?? ''));
        ?>
        <div class="wrap">
            <h1>InsightOS</h1>
            <?php if ($notice !== '') : ?>
                <div class="notice <?php echo $notice === 'connected' || $notice === 'disconnected' ? 'notice-success' : 'notice-error'; ?> is-dismissible">
                    <p><?php echo esc_html($this->notice_message($notice)); ?></p>
                </div>
            <?php endif; ?>

            <?php if ($connected) : ?>
                <h2>Website connected</h2>
                <p>InsightOS can test this connection. Website changes still require the approvals saved in InsightOS.</p>
                <form method="post" action="<?php echo esc_url(admin_url('admin-post.php')); ?>">
                    <input type="hidden" name="action" value="lsos_disconnect_site" />
                    <?php wp_nonce_field('lsos_disconnect_site'); ?>
                    <?php submit_button('Disconnect website', 'secondary'); ?>
                </form>
                <hr />
                <h2>Replace the connection key</h2>
            <?php else : ?>
                <h2>Connect this website</h2>
            <?php endif; ?>
                <ol>
                    <li>Open this business in InsightOS and choose <strong>Create pairing code</strong>.</li>
                    <li>Enter the one-time code below.</li>
                    <li>Choose <strong>Connect website</strong>.</li>
                </ol>
                <p>You never need to share your WordPress administrator password with InsightOS.</p>
                <form method="post" action="<?php echo esc_url(admin_url('admin-post.php')); ?>">
                    <input type="hidden" name="action" value="lsos_pair_site" />
                    <?php wp_nonce_field('lsos_pair_site'); ?>
                    <table class="form-table" role="presentation">
                        <tr>
                            <th scope="row"><label for="lsos_pairing_code">Pairing code</label></th>
                            <td><input name="pairing_code" id="lsos_pairing_code" type="text" class="regular-text code" autocomplete="one-time-code" required /></td>
                        </tr>
                    </table>
                    <?php submit_button('Connect website'); ?>
                </form>
        </div>
        <?php
    }

    public function pair_site(): void
    {
        $this->require_admin('lsos_pair_site');
        $pairing_code = sanitize_text_field((string) ($_POST['pairing_code'] ?? ''));
        if ($pairing_code === '') {
            $this->redirect_with_notice('invalid');
        }

        $response = wp_remote_post($this->pairing_endpoint(), array(
            'timeout' => 20,
            'headers' => array('Content-Type' => 'application/json'),
            'body' => wp_json_encode(array(
                'pairing_code' => $pairing_code,
                'site_url' => site_url(),
                'plugin_version' => LSOS_EXECUTION_PLUGIN_VERSION,
            )),
        ));
        if (is_wp_error($response)) {
            $this->redirect_with_notice('unreachable');
        }

        $status = (int) wp_remote_retrieve_response_code($response);
        $payload = json_decode((string) wp_remote_retrieve_body($response), true);
        $data = is_array($payload) && isset($payload['data']) && is_array($payload['data']) ? $payload['data'] : array();
        $token = trim((string) ($data['plugin_token'] ?? ''));
        $secret = trim((string) ($data['shared_secret'] ?? ''));
        if ($status < 200 || $status >= 300 || $token === '' || $secret === '') {
            $this->redirect_with_notice($status === 410 ? 'expired' : 'invalid');
        }

        update_option('lsos_execution_plugin_token', $token, false);
        update_option('lsos_execution_plugin_shared_secret', $secret, false);
        delete_option('lsos_execution_plugin_disconnected');
        $this->redirect_with_notice('connected');
    }

    public function disconnect_site(): void
    {
        $this->require_admin('lsos_disconnect_site');
        self::clear_credentials();
        $this->redirect_with_notice('disconnected');
    }

    public static function clear_credentials(): void
    {
        delete_option('lsos_execution_plugin_token');
        delete_option('lsos_execution_plugin_shared_secret');
        update_option('lsos_execution_plugin_disconnected', '1', false);
    }

    private function require_admin(string $action): void
    {
        if (! current_user_can('manage_options')) {
            wp_die('You are not allowed to change the InsightOS connection.');
        }
        check_admin_referer($action);
    }

    private function pairing_endpoint(): string
    {
        if (defined('LSOS_PAIRING_ENDPOINT')) {
            return esc_url_raw((string) LSOS_PAIRING_ENDPOINT);
        }
        return esc_url_raw((string) apply_filters(
            'lsos_pairing_endpoint',
            'https://insightos.verixlabs.com/api/v1/provider-health/wordpress-pairing/exchange'
        ));
    }

    private function is_connected(): bool
    {
        if ((string) get_option('lsos_execution_plugin_disconnected', '') === '1') {
            return false;
        }
        $token = trim((string) get_option('lsos_execution_plugin_token', ''));
        $secret = trim((string) get_option('lsos_execution_plugin_shared_secret', ''));
        if ($token !== '' && $secret !== '') {
            return true;
        }
        return defined('LSOS_EXECUTION_PLUGIN_TOKEN')
            && trim((string) LSOS_EXECUTION_PLUGIN_TOKEN) !== ''
            && defined('LSOS_EXECUTION_PLUGIN_SHARED_SECRET')
            && trim((string) LSOS_EXECUTION_PLUGIN_SHARED_SECRET) !== '';
    }

    private function notice_message(string $notice): string
    {
        $messages = array(
            'connected' => 'This website is connected to InsightOS.',
            'disconnected' => 'The InsightOS connection keys were removed from this website.',
            'expired' => 'That code expired. Create a new pairing code in InsightOS.',
            'unreachable' => 'InsightOS could not be reached. Check the website connection and try again.',
            'invalid' => 'That code could not connect this website. Create a new code in InsightOS and try again.',
        );
        return (string) ($messages[$notice] ?? $messages['invalid']);
    }

    private function redirect_with_notice(string $notice): void
    {
        wp_safe_redirect(add_query_arg(
            array('page' => 'lsos-execution-plugin', 'lsos_notice' => $notice),
            admin_url('options-general.php')
        ));
        exit;
    }
}
