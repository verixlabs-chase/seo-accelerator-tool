<?php

if (! defined('ABSPATH')) {
    exit;
}

class LSOS_Execution_Plugin
{
    private static ?LSOS_Execution_Plugin $instance = null;
    private LSOS_Auth $auth;
    private LSOS_Audit_Store $audit_store;
    private LSOS_DOM_Mutation_Engine $mutation_engine;
    private LSOS_REST_Controller $rest_controller;
    private LSOS_Settings_Page $settings_page;

    public static function instance(): LSOS_Execution_Plugin
    {
        if (self::$instance === null) {
            self::$instance = new self();
        }

        return self::$instance;
    }

    private function __construct()
    {
        LSOS_Audit_Store::maybe_upgrade();
        $this->auth = new LSOS_Auth();
        $this->audit_store = new LSOS_Audit_Store();
        $this->mutation_engine = new LSOS_DOM_Mutation_Engine($this->audit_store);
        $this->rest_controller = new LSOS_REST_Controller($this->auth, $this->audit_store, $this->mutation_engine);
        $this->settings_page = new LSOS_Settings_Page();

        add_action('rest_api_init', array($this->rest_controller, 'register_routes'));
        add_filter('pre_get_document_title', array($this, 'render_meta_title'), 99);
        add_action('wp_head', array($this, 'render_meta_description'), 1);
        add_action('wp_head', array($this, 'render_schema_markup'), 100);
        $this->settings_page->register();
    }

    public function render_meta_title(string $current_title): string
    {
        if (! is_singular()) {
            return $current_title;
        }

        $post_id = get_queried_object_id();
        $saved_title = $post_id ? trim((string) get_post_meta($post_id, '_lsos_meta_title', true)) : '';
        return $saved_title !== '' ? $saved_title : $current_title;
    }

    public function render_meta_description(): void
    {
        if (! is_singular()) {
            return;
        }

        $post_id = get_queried_object_id();
        $description = $post_id
            ? trim((string) get_post_meta($post_id, '_lsos_meta_description', true))
            : '';
        if ($description === '') {
            return;
        }

        echo '<meta name="description" content="' . esc_attr($description) . '">' . "\n";
    }

    public function render_schema_markup(): void
    {
        if (! is_singular()) {
            return;
        }

        $post_id = get_queried_object_id();
        if (! $post_id) {
            return;
        }

        $raw = get_post_meta($post_id, '_lsos_schema_markup', true);
        if (empty($raw)) {
            return;
        }

        $payload = is_array($raw) ? $raw : json_decode((string) $raw, true);
        if (! is_array($payload)) {
            return;
        }

        $items = array_values(array_filter(isset($payload[0]) ? $payload : array($payload), 'is_array'));
        foreach ($items as $item) {
            echo '<script type="application/ld+json">' . wp_json_encode($item, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE) . '</script>' . "
";
        }
    }
}
