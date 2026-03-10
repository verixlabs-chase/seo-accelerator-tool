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

    public static function instance(): LSOS_Execution_Plugin
    {
        if (self::$instance === null) {
            self::$instance = new self();
        }

        return self::$instance;
    }

    private function __construct()
    {
        $this->auth = new LSOS_Auth();
        $this->audit_store = new LSOS_Audit_Store();
        $this->mutation_engine = new LSOS_DOM_Mutation_Engine($this->audit_store);
        $this->rest_controller = new LSOS_REST_Controller($this->auth, $this->audit_store, $this->mutation_engine);

        add_action('rest_api_init', array($this->rest_controller, 'register_routes'));
        add_action('wp_head', array($this, 'render_schema_markup'), 100);
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
