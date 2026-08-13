<?php

if (! defined('ABSPATH')) {
    exit;
}

class LSOS_REST_Controller
{
    private const MAX_MUTATIONS_PER_REQUEST = 20;

    private LSOS_Auth $auth;
    private LSOS_Audit_Store $audit_store;
    private LSOS_DOM_Mutation_Engine $mutation_engine;

    public function __construct(LSOS_Auth $auth, LSOS_Audit_Store $audit_store, LSOS_DOM_Mutation_Engine $mutation_engine)
    {
        $this->auth = $auth;
        $this->audit_store = $audit_store;
        $this->mutation_engine = $mutation_engine;
    }

    public function register_routes(): void
    {
        register_rest_route('lsos/v1', '/health', array(
            'methods' => WP_REST_Server::CREATABLE,
            'callback' => array($this, 'connection_health'),
            'permission_callback' => array($this, 'authorize'),
        ));

        register_rest_route('lsos/v1', '/mutations/apply', array(
            'methods' => WP_REST_Server::CREATABLE,
            'callback' => array($this, 'apply_mutations'),
            'permission_callback' => array($this, 'authorize'),
        ));

        register_rest_route('lsos/v1', '/mutations/preview', array(
            'methods' => WP_REST_Server::CREATABLE,
            'callback' => array($this, 'preview_mutations'),
            'permission_callback' => array($this, 'authorize'),
        ));

        register_rest_route('lsos/v1', '/mutations/rollback', array(
            'methods' => WP_REST_Server::CREATABLE,
            'callback' => array($this, 'rollback_mutations'),
            'permission_callback' => array($this, 'authorize'),
        ));

        register_rest_route('lsos/v1', '/connection/disconnect', array(
            'methods' => WP_REST_Server::CREATABLE,
            'callback' => array($this, 'disconnect_connection'),
            'permission_callback' => array($this, 'authorize'),
        ));

        register_rest_route('lsos/v1', '/content/inventory', array(
            'methods' => WP_REST_Server::CREATABLE,
            'callback' => array($this, 'content_inventory'),
            'permission_callback' => array($this, 'authorize'),
        ));
    }

    public function authorize(WP_REST_Request $request)
    {
        return $this->auth->authorize_request($request);
    }

    public function connection_health(WP_REST_Request $request): WP_REST_Response
    {
        return new WP_REST_Response(array(
            'plugin_version' => LSOS_EXECUTION_PLUGIN_VERSION,
            'wordpress_version' => (string) get_bloginfo('version'),
            'php_version' => PHP_VERSION,
            'site_url' => site_url(),
            'home_url' => home_url(),
            'permissions' => array(
                'mutations' => true,
                'change_preview' => true,
                'rollback' => true,
                'health_check' => true,
                'content_inventory' => true,
            ),
            'supported_actions' => array(
                'update_meta_title',
                'update_meta_description',
                'insert_internal_link',
                'create_internal_anchor',
                'add_schema_markup',
                'publish_content_page',
            ),
        ), 200);
    }

    public function disconnect_connection(WP_REST_Request $request): WP_REST_Response
    {
        LSOS_Settings_Page::clear_credentials();
        return new WP_REST_Response(array(
            'plugin_version' => LSOS_EXECUTION_PLUGIN_VERSION,
            'disconnected' => true,
        ), 200);
    }

    public function content_inventory(WP_REST_Request $request): WP_REST_Response
    {
        $payload = $request->get_json_params();
        $page = max(1, (int) ($payload['page'] ?? 1));
        $per_page = min(50, max(1, (int) ($payload['per_page'] ?? 25)));
        $post_types = array_values(array_filter(
            get_post_types(array('public' => true), 'names'),
            static fn ($post_type): bool => $post_type !== 'attachment'
        ));
        $query = new WP_Query(array(
            'post_type' => $post_types,
            'post_status' => array('publish', 'draft', 'pending', 'private', 'future'),
            'posts_per_page' => $per_page,
            'paged' => $page,
            'orderby' => 'ID',
            'order' => 'ASC',
            'no_found_rows' => false,
        ));

        $items = array();
        foreach ($query->posts as $post) {
            if ($post instanceof WP_Post) {
                $items[] = $this->inventory_item($post);
            }
        }

        return new WP_REST_Response(array(
            'plugin_version' => LSOS_EXECUTION_PLUGIN_VERSION,
            'wordpress_version' => (string) get_bloginfo('version'),
            'php_version' => PHP_VERSION,
            'site_url' => site_url(),
            'page' => $page,
            'per_page' => $per_page,
            'total_items' => (int) $query->found_posts,
            'total_pages' => (int) $query->max_num_pages,
            'seo_plugins' => $this->active_seo_plugins(),
            'items' => $items,
        ), 200);
    }

    public function apply_mutations(WP_REST_Request $request): WP_REST_Response
    {
        $payload = $request->get_json_params();
        $mutations = isset($payload['mutations']) && is_array($payload['mutations']) ? array_values($payload['mutations']) : array();
        if (empty($mutations)) {
            return new WP_REST_Response(array('message' => 'No mutations supplied.'), 400);
        }
        if (count($mutations) > self::MAX_MUTATIONS_PER_REQUEST) {
            return new WP_REST_Response(array('message' => 'Mutation batch exceeds the maximum size.'), 422);
        }

        $execution_id = (string) ($payload['execution_id'] ?? '');
        $signature = (string) $request->get_header('x-lsos-signature');
        $results = array();

        try {
            foreach ($mutations as $mutation) {
                $this->mutation_engine->assert_preview_is_current($mutation);
            }
        } catch (Throwable $throwable) {
            return new WP_REST_Response(array(
                'message' => 'This page changed after the preview. Check the changes again before running them.',
                'reason_code' => 'wordpress_preview_stale',
                'details' => $throwable->getMessage(),
            ), 409);
        }

        foreach ($mutations as $mutation) {
            $mutation_id = (string) ($mutation['mutation_id'] ?? '');
            $existing = $mutation_id !== '' ? $this->audit_store->get_mutation($mutation_id) : null;
            if (is_array($existing) && in_array((string) $existing['status'], array('applied', 'skipped_duplicate'), true)) {
                $results[] = array(
                    'mutation_id' => $existing['mutation_id'],
                    'status' => $existing['status'],
                    'mutation_type' => $existing['mutation_type'],
                    'target_url' => $existing['target_url'],
                    'before_state' => $existing['before_state'],
                    'after_state' => $existing['after_state'],
                    'rollback_payload' => $existing['rollback_payload'],
                );
                continue;
            }

            try {
                $result = $this->mutation_engine->apply_mutation($mutation);
                $this->audit_store->record_mutation(array(
                    'mutation_id' => $result['mutation_id'],
                    'execution_id' => $execution_id,
                    'mutation_type' => $result['mutation_type'],
                    'source_url' => $mutation['source_url'] ?? null,
                    'target_url' => $result['target_url'],
                    'status' => $result['status'],
                    'before_state' => $result['before_state'],
                    'after_state' => $result['after_state'],
                    'rollback_payload' => $result['rollback_payload'],
                    'request_signature' => $signature,
                ));
                $results[] = $result;
            } catch (Throwable $throwable) {
                $results[] = array(
                    'mutation_id' => $mutation_id,
                    'status' => 'failed',
                    'mutation_type' => (string) ($mutation['action'] ?? ''),
                    'target_url' => (string) ($mutation['target_url'] ?? ''),
                    'before_state' => array(),
                    'after_state' => array(),
                    'rollback_payload' => array(),
                    'error' => $throwable->getMessage(),
                );
            }
        }

        return new WP_REST_Response(array(
            'plugin_version' => LSOS_EXECUTION_PLUGIN_VERSION,
            'delivery_mode' => 'wordpress_plugin',
            'results' => $results,
        ), 200);
    }

    public function preview_mutations(WP_REST_Request $request): WP_REST_Response
    {
        $payload = $request->get_json_params();
        $mutations = isset($payload['mutations']) && is_array($payload['mutations']) ? array_values($payload['mutations']) : array();
        if (empty($mutations)) {
            return new WP_REST_Response(array('message' => 'No mutations supplied.'), 400);
        }
        if (count($mutations) > self::MAX_MUTATIONS_PER_REQUEST) {
            return new WP_REST_Response(array('message' => 'Mutation batch exceeds the maximum size.'), 422);
        }

        $results = array();
        foreach ($mutations as $mutation) {
            try {
                $results[] = $this->mutation_engine->preview_mutation($mutation);
            } catch (Throwable $throwable) {
                $results[] = array(
                    'mutation_id' => (string) ($mutation['mutation_id'] ?? ''),
                    'mutation_type' => (string) ($mutation['action'] ?? ''),
                    'target_url' => (string) ($mutation['source_url'] ?? $mutation['target_url'] ?? ''),
                    'before' => array(),
                    'after' => array(),
                    'expected_version' => array(
                        'revision_id' => 'unavailable',
                        'content_hash' => hash('sha256', 'unavailable'),
                    ),
                    'validation_checks' => array(
                        array('code' => 'preview_failed', 'passed' => false, 'message' => 'This change could not be checked safely.'),
                    ),
                    'conflicts' => array(
                        array('code' => 'preview_failed', 'message' => $throwable->getMessage(), 'recovery' => 'Check the page and create a new preview.'),
                    ),
                    'rollback_plan' => array('available' => false, 'summary' => 'No change will run while this conflict remains.'),
                );
            }
        }

        return new WP_REST_Response(array(
            'plugin_version' => LSOS_EXECUTION_PLUGIN_VERSION,
            'site_url' => site_url(),
            'delivery_mode' => 'wordpress_plugin_preview',
            'results' => $results,
        ), 200);
    }

    public function rollback_mutations(WP_REST_Request $request): WP_REST_Response
    {
        $payload = $request->get_json_params();
        $mutations = isset($payload['mutations']) && is_array($payload['mutations']) ? array_values($payload['mutations']) : array();
        if (empty($mutations)) {
            return new WP_REST_Response(array('message' => 'No rollback mutations supplied.'), 400);
        }

        $results = array();
        foreach ($mutations as $mutation) {
            $mutation_id = (string) ($mutation['mutation_id'] ?? '');
            $stored = $mutation_id !== '' ? $this->audit_store->get_mutation($mutation_id) : null;
            $merged = is_array($stored) ? array_merge($stored, $mutation) : $mutation;
            try {
                $result = $this->mutation_engine->rollback_mutation($merged);
                $this->audit_store->mark_rolled_back($mutation_id, $result['after_state']);
                $results[] = $result;
            } catch (Throwable $throwable) {
                $results[] = array(
                    'mutation_id' => $mutation_id,
                    'status' => 'failed',
                    'mutation_type' => (string) ($merged['mutation_type'] ?? ''),
                    'target_url' => (string) ($merged['target_url'] ?? ''),
                    'before_state' => isset($merged['before_state']) && is_array($merged['before_state']) ? $merged['before_state'] : array(),
                    'after_state' => array(),
                    'rollback_payload' => isset($merged['rollback_payload']) && is_array($merged['rollback_payload']) ? $merged['rollback_payload'] : array(),
                    'error' => $throwable->getMessage(),
                );
            }
        }

        return new WP_REST_Response(array(
            'plugin_version' => LSOS_EXECUTION_PLUGIN_VERSION,
            'delivery_mode' => 'wordpress_plugin',
            'results' => $results,
        ), 200);
    }

    private function inventory_item(WP_Post $post): array
    {
        $content = (string) $post->post_content;
        $meta_title = $this->first_saved_meta($post->ID, array(
            '_lsos_meta_title',
            '_yoast_wpseo_title',
            'rank_math_title',
            '_aioseo_title',
        ));
        $meta_description = $this->first_saved_meta($post->ID, array(
            '_lsos_meta_description',
            '_yoast_wpseo_metadesc',
            'rank_math_description',
            '_aioseo_description',
        ));
        $canonical = $this->first_saved_meta($post->ID, array(
            '_lsos_canonical_url',
            '_yoast_wpseo_canonical',
            'rank_math_canonical_url',
            '_aioseo_canonical_url',
        ));
        $schema_types = $this->schema_types($post->ID);
        $revisions = wp_get_post_revisions($post->ID, array(
            'posts_per_page' => 1,
            'orderby' => 'ID',
            'order' => 'DESC',
        ));
        $latest_revision = ! empty($revisions) ? reset($revisions) : null;
        $revision_id = $latest_revision instanceof WP_Post
            ? 'revision:' . (string) $latest_revision->ID
            : 'modified:' . (string) $post->post_modified_gmt;
        $fingerprint = wp_json_encode(array(
            'title' => (string) $post->post_title,
            'content' => $content,
            'meta_title' => $meta_title,
            'meta_description' => $meta_description,
            'canonical' => $canonical,
            'status' => (string) $post->post_status,
        ));

        return array(
            'wp_post_id' => (int) $post->ID,
            'post_type' => (string) $post->post_type,
            'publication_status' => (string) $post->post_status,
            'slug' => (string) $post->post_name,
            'url' => (string) get_permalink($post),
            'title' => (string) get_the_title($post),
            'meta_title' => $meta_title,
            'meta_description' => $meta_description,
            'canonical_url' => $canonical,
            'headings' => $this->extract_headings($content),
            'internal_links' => $this->extract_internal_links($content),
            'schema_types' => $schema_types,
            'schema_present' => ! empty($schema_types),
            'word_count' => str_word_count(wp_strip_all_tags(strip_shortcodes($content))),
            'revision_id' => $revision_id,
            'content_hash' => hash('sha256', (string) $fingerprint),
            'modified_at' => get_post_modified_time('c', true, $post),
        );
    }

    private function first_saved_meta(int $post_id, array $keys): string
    {
        foreach ($keys as $key) {
            $value = trim((string) get_post_meta($post_id, $key, true));
            if ($value !== '') {
                return $value;
            }
        }
        return '';
    }

    private function extract_headings(string $content): array
    {
        if (! preg_match_all('/<h([1-6])[^>]*>(.*?)<\/h\1>/is', $content, $matches, PREG_SET_ORDER)) {
            return array();
        }
        $headings = array();
        foreach (array_slice($matches, 0, 40) as $match) {
            $text = trim(wp_strip_all_tags((string) $match[2]));
            if ($text !== '') {
                $headings[] = array('level' => (int) $match[1], 'text' => $text);
            }
        }
        return $headings;
    }

    private function extract_internal_links(string $content): array
    {
        if (! preg_match_all('/<a[^>]+href=["\']([^"\']+)["\']/i', $content, $matches)) {
            return array();
        }
        $site_host = preg_replace('/^www\./', '', strtolower((string) wp_parse_url(home_url(), PHP_URL_HOST)));
        $links = array();
        foreach ($matches[1] as $href) {
            $url = esc_url_raw((string) $href);
            if ($url === '') {
                continue;
            }
            $scheme = strtolower((string) wp_parse_url($url, PHP_URL_SCHEME));
            if ($scheme !== '' && ! in_array($scheme, array('http', 'https'), true)) {
                continue;
            }
            $host = preg_replace('/^www\./', '', strtolower((string) wp_parse_url($url, PHP_URL_HOST)));
            if ($host !== '' && $host !== $site_host) {
                continue;
            }
            $links[] = $host === '' ? home_url('/' . ltrim($url, '/')) : $url;
            if (count($links) >= 100) {
                break;
            }
        }
        return array_values(array_unique($links));
    }

    private function schema_types(int $post_id): array
    {
        $types = array();
        $raw = get_post_meta($post_id, '_lsos_schema_markup', true);
        $decoded = is_array($raw) ? $raw : json_decode((string) $raw, true);
        $this->collect_schema_types($decoded, $types);
        foreach (array_keys(get_post_meta($post_id)) as $key) {
            if (strpos((string) $key, 'rank_math_schema_') === 0) {
                $types[] = 'Rank Math schema';
                break;
            }
        }
        return array_values(array_unique(array_slice($types, 0, 20)));
    }

    private function collect_schema_types($value, array &$types): void
    {
        if (! is_array($value)) {
            return;
        }
        if (isset($value['@type'])) {
            foreach ((array) $value['@type'] as $type) {
                $normalized = sanitize_text_field((string) $type);
                if ($normalized !== '') {
                    $types[] = $normalized;
                }
            }
        }
        foreach ($value as $child) {
            if (is_array($child)) {
                $this->collect_schema_types($child, $types);
            }
        }
    }

    private function active_seo_plugins(): array
    {
        $plugins = array();
        if (defined('WPSEO_VERSION')) {
            $plugins[] = array('name' => 'Yoast SEO', 'version' => (string) WPSEO_VERSION);
        }
        if (defined('RANK_MATH_VERSION')) {
            $plugins[] = array('name' => 'Rank Math', 'version' => (string) RANK_MATH_VERSION);
        }
        if (defined('AIOSEO_VERSION')) {
            $plugins[] = array('name' => 'All in One SEO', 'version' => (string) AIOSEO_VERSION);
        }
        return $plugins;
    }
}
