<?php

if (! defined('ABSPATH')) {
    exit;
}

class LSOS_DOM_Mutation_Engine
{
    private const SUPPORTED_ACTIONS = array(
        'update_meta_title',
        'update_meta_description',
        'insert_internal_link',
        'create_internal_anchor',
        'add_schema_markup',
        'publish_content_page',
    );

    private const PROTECTED_PATH_PREFIXES = array('/wp-admin', '/wp-login.php', '/checkout', '/cart');
    private const SELECTOR_PATTERN = "/^[A-Za-z0-9#._:\\-\\[\\]=\"'\\s>+~(),]+$/";

    private LSOS_Audit_Store $audit_store;

    public function __construct(LSOS_Audit_Store $audit_store)
    {
        $this->audit_store = $audit_store;
    }

    public function apply_mutation(array $mutation): array
    {
        $this->validate_mutation($mutation);

        switch ((string) $mutation['action']) {
            case 'update_meta_title':
                return $this->update_meta_title($mutation);
            case 'update_meta_description':
                return $this->update_meta_description($mutation);
            case 'insert_internal_link':
                return $this->insert_internal_link($mutation);
            case 'create_internal_anchor':
                return $this->create_internal_anchor($mutation);
            case 'add_schema_markup':
                return $this->add_schema_markup($mutation);
            case 'publish_content_page':
                return $this->publish_content_page($mutation);
        }

        throw new RuntimeException('Unsupported mutation action.');
    }

    public function preview_mutation(array $mutation): array
    {
        $this->validate_mutation($mutation);
        $action = (string) $mutation['action'];
        $target_url = (string) ($mutation['source_url'] ?? $mutation['target_url'] ?? '/');
        $payload = $this->payload($mutation);
        $post = null;
        $before = array();
        $conflicts = array();

        if ($action === 'publish_content_page') {
            $slug = sanitize_title((string) ($payload['slug'] ?? $payload['title'] ?? ''));
            $existing = $slug !== '' ? get_page_by_path($slug, OBJECT, get_post_types(array('public' => true), 'names')) : null;
            if ($existing instanceof WP_Post) {
                $conflicts[] = array(
                    'code' => 'target_already_exists',
                    'message' => 'A WordPress page already uses this address.',
                    'recovery' => 'Choose a different page address or update the existing page instead.',
                );
            }
            $expected_version = array(
                'revision_id' => 'new:' . $slug,
                'content_hash' => hash('sha256', 'new:' . $slug . ':' . ($existing instanceof WP_Post ? (string) $existing->ID : 'available')),
            );
            $before = array('page_exists' => $existing instanceof WP_Post, 'slug' => $slug);
        } else {
            $post = $this->resolve_post_by_url($target_url);
            $expected_version = $this->post_version($post);
            $before = $this->preview_before_state($post, $action);
        }

        return array(
            'mutation_id' => (string) ($mutation['mutation_id'] ?? ''),
            'mutation_type' => $action,
            'target_url' => $target_url,
            'before' => $before,
            'after' => $this->preview_after_state($action, $payload),
            'expected_version' => $expected_version,
            'validation_checks' => array(
                array('code' => 'target_checked', 'passed' => true, 'message' => 'The target page was checked.'),
                array('code' => 'change_supported', 'passed' => true, 'message' => 'This type of change is supported.'),
                array('code' => 'rollback_available', 'passed' => true, 'message' => 'The current value can be saved for rollback.'),
            ),
            'conflicts' => $conflicts,
            'rollback_plan' => array(
                'available' => true,
                'summary' => $action === 'publish_content_page'
                    ? 'Delete the draft page created by this change.'
                    : 'Restore the exact WordPress values captured immediately before the change.',
            ),
        );
    }

    public function assert_preview_is_current(array $mutation): void
    {
        $expected = isset($mutation['expected_version']) && is_array($mutation['expected_version']) ? $mutation['expected_version'] : array();
        if (empty($expected['revision_id']) || empty($expected['content_hash'])) {
            throw new RuntimeException('An approved page version is required.');
        }
        $action = (string) ($mutation['action'] ?? '');
        $payload = $this->payload($mutation);
        if ($action === 'publish_content_page') {
            $slug = sanitize_title((string) ($payload['slug'] ?? $payload['title'] ?? ''));
            $existing = $slug !== '' ? get_page_by_path($slug, OBJECT, get_post_types(array('public' => true), 'names')) : null;
            $current = array(
                'revision_id' => 'new:' . $slug,
                'content_hash' => hash('sha256', 'new:' . $slug . ':' . ($existing instanceof WP_Post ? (string) $existing->ID : 'available')),
            );
        } else {
            $target_url = (string) ($mutation['source_url'] ?? $mutation['target_url'] ?? '/');
            $current = $this->post_version($this->resolve_post_by_url($target_url));
        }
        if (! hash_equals((string) $expected['revision_id'], (string) $current['revision_id']) || ! hash_equals((string) $expected['content_hash'], (string) $current['content_hash'])) {
            throw new RuntimeException('The WordPress page revision no longer matches the approved preview.');
        }
    }

    public function rollback_mutation(array $mutation): array
    {
        $rollback = isset($mutation['rollback_payload']) && is_array($mutation['rollback_payload']) ? $mutation['rollback_payload'] : array();
        $action = (string) ($mutation['mutation_type'] ?? $rollback['action'] ?? '');
        $mutation_id = (string) ($mutation['mutation_id'] ?? '');

        switch ($action) {
            case 'update_meta_title':
            case 'update_meta_description':
            case 'insert_internal_link':
            case 'create_internal_anchor':
            case 'add_schema_markup':
                $post_id = (int) ($rollback['post_id'] ?? 0);
                if ($post_id <= 0) {
                    throw new RuntimeException('Rollback payload is missing post_id.');
                }
                $this->restore_post_state($post_id, $rollback);
                break;
            case 'publish_content_page':
                $created_post_id = (int) ($rollback['created_post_id'] ?? 0);
                if ($created_post_id > 0) {
                    wp_delete_post($created_post_id, true);
                }
                break;
            default:
                throw new RuntimeException('Unsupported rollback action.');
        }

        return array(
            'mutation_id' => $mutation_id,
            'status' => 'rolled_back',
            'mutation_type' => $action,
            'target_url' => (string) ($mutation['target_url'] ?? ''),
            'before_state' => isset($mutation['before_state']) && is_array($mutation['before_state']) ? $mutation['before_state'] : array(),
            'after_state' => array('rolled_back' => true),
            'rollback_payload' => $rollback,
        );
    }

    private function update_meta_title(array $mutation): array
    {
        $post = $this->resolve_post_by_url((string) $mutation['target_url']);
        $payload = $this->payload($mutation);
        $title = sanitize_text_field((string) ($payload['title'] ?? $payload['value'] ?? ''));
        if ($title === '') {
            throw new RuntimeException('Meta title payload is required.');
        }

        $before = $this->snapshot_post_state($post->ID, true, false, false, false);
        update_post_meta($post->ID, '_lsos_meta_title', $title);
        update_post_meta($post->ID, '_yoast_wpseo_title', $title);
        update_post_meta($post->ID, 'rank_math_title', $title);
        update_post_meta($post->ID, '_aioseo_title', $title);
        if (! empty($payload['sync_post_title'])) {
            wp_update_post(array('ID' => $post->ID, 'post_title' => $title));
        }

        $after = $this->snapshot_post_state($post->ID, true, false, false, false);
        return $this->result($mutation, 'applied', $before, $after, $this->build_rollback_payload('update_meta_title', $post->ID, $before));
    }

    private function update_meta_description(array $mutation): array
    {
        $post = $this->resolve_post_by_url((string) $mutation['target_url']);
        $payload = $this->payload($mutation);
        $description = sanitize_textarea_field((string) ($payload['description'] ?? $payload['value'] ?? ''));
        if ($description === '') {
            throw new RuntimeException('Meta description payload is required.');
        }

        $before = $this->snapshot_post_state($post->ID, false, true, false, false);
        update_post_meta($post->ID, '_lsos_meta_description', $description);
        update_post_meta($post->ID, '_yoast_wpseo_metadesc', $description);
        update_post_meta($post->ID, 'rank_math_description', $description);
        update_post_meta($post->ID, '_aioseo_description', $description);
        $after = $this->snapshot_post_state($post->ID, false, true, false, false);

        return $this->result($mutation, 'applied', $before, $after, $this->build_rollback_payload('update_meta_description', $post->ID, $before));
    }

    private function insert_internal_link(array $mutation): array
    {
        $payload = $this->payload($mutation);
        $source_url = (string) ($mutation['source_url'] ?? $payload['source_url'] ?? '');
        $anchor_text = trim((string) ($payload['anchor_text'] ?? ''));
        if ($source_url === '' || $anchor_text === '') {
            throw new RuntimeException('insert_internal_link requires source_url and anchor_text.');
        }

        $source_post = $this->resolve_post_by_url($source_url);
        $target_url = $this->normalize_url((string) ($payload['target_url'] ?? $mutation['target_url']));
        $before = $this->snapshot_post_state($source_post->ID, false, false, true, false);
        $updated_content = $this->apply_anchor_in_content((string) $source_post->post_content, $anchor_text, $target_url, (string) ($payload['selector'] ?? ''));

        if ($updated_content === (string) $source_post->post_content) {
            return $this->result($mutation, 'skipped_duplicate', $before, $before, $this->build_rollback_payload('insert_internal_link', $source_post->ID, $before, $source_url));
        }

        wp_update_post(array('ID' => $source_post->ID, 'post_content' => $updated_content));
        $after = $this->snapshot_post_state($source_post->ID, false, false, true, false);
        return $this->result($mutation, 'applied', $before, $after, $this->build_rollback_payload('insert_internal_link', $source_post->ID, $before, $source_url));
    }

    private function create_internal_anchor(array $mutation): array
    {
        $payload = $this->payload($mutation);
        $source_url = (string) ($mutation['source_url'] ?? $mutation['target_url']);
        $anchor_id = sanitize_title((string) ($payload['anchor_id'] ?? $payload['anchor_text'] ?? ''));
        if ($anchor_id === '') {
            throw new RuntimeException('create_internal_anchor requires anchor_id or anchor_text.');
        }

        $post = $this->resolve_post_by_url($source_url);
        $before = $this->snapshot_post_state($post->ID, false, false, true, false);
        $updated_content = $this->inject_anchor_id((string) $post->post_content, $anchor_id, (string) ($payload['selector'] ?? ''));
        if ($updated_content === (string) $post->post_content) {
            return $this->result($mutation, 'skipped_duplicate', $before, $before, $this->build_rollback_payload('create_internal_anchor', $post->ID, $before, $source_url));
        }

        wp_update_post(array('ID' => $post->ID, 'post_content' => $updated_content));
        $after = $this->snapshot_post_state($post->ID, false, false, true, false);
        return $this->result($mutation, 'applied', $before, $after, $this->build_rollback_payload('create_internal_anchor', $post->ID, $before, $source_url));
    }

    private function add_schema_markup(array $mutation): array
    {
        $post = $this->resolve_post_by_url((string) $mutation['target_url']);
        $payload = $this->payload($mutation);
        $schema = $payload['schema'] ?? $payload['schema_json'] ?? $payload['value'] ?? null;
        if (! is_array($schema)) {
            throw new RuntimeException('add_schema_markup requires a schema object payload.');
        }

        $before = $this->snapshot_post_state($post->ID, false, false, false, true);
        update_post_meta($post->ID, '_lsos_schema_markup', wp_json_encode($schema, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE));
        $after = $this->snapshot_post_state($post->ID, false, false, false, true);
        return $this->result($mutation, 'applied', $before, $after, $this->build_rollback_payload('add_schema_markup', $post->ID, $before));
    }

    private function publish_content_page(array $mutation): array
    {
        $payload = $this->payload($mutation);
        $title = sanitize_text_field((string) ($payload['title'] ?? ''));
        if ($title === '') {
            throw new RuntimeException('publish_content_page requires title.');
        }

        $post_id = wp_insert_post(
            array(
                'post_type' => sanitize_key((string) ($payload['post_type'] ?? 'page')),
                'post_status' => sanitize_key((string) ($payload['status'] ?? $payload['publication_state'] ?? 'draft')),
                'post_title' => $title,
                'post_content' => $this->content_from_payload($payload),
                'post_name' => sanitize_title((string) ($payload['slug'] ?? $title)),
            ),
            true
        );
        if (is_wp_error($post_id)) {
            throw new RuntimeException($post_id->get_error_message());
        }

        $seo = isset($payload['seo']) && is_array($payload['seo']) ? $payload['seo'] : array();
        $meta_title = (string) ($payload['meta_title'] ?? $seo['meta_title'] ?? '');
        $meta_description = (string) ($payload['meta_description'] ?? $seo['meta_description'] ?? '');
        if ($meta_title !== '') {
            update_post_meta($post_id, '_lsos_meta_title', sanitize_text_field($meta_title));
        }
        if ($meta_description !== '') {
            update_post_meta($post_id, '_lsos_meta_description', sanitize_textarea_field($meta_description));
        }
        if (! empty($payload['schema']) && is_array($payload['schema'])) {
            update_post_meta($post_id, '_lsos_schema_markup', wp_json_encode($payload['schema'], JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE));
        }

        return $this->result(
            $mutation,
            'applied',
            array(),
            array('post_id' => $post_id, 'target_url' => get_permalink($post_id), 'post_title' => get_the_title($post_id)),
            array('action' => 'publish_content_page', 'created_post_id' => $post_id)
        );
    }

    private function validate_mutation(array $mutation): void
    {
        $action = (string) ($mutation['action'] ?? '');
        if (! in_array($action, self::SUPPORTED_ACTIONS, true)) {
            throw new RuntimeException('Unsupported mutation action: ' . $action);
        }

        $target_url = $this->normalize_url((string) ($mutation['target_url'] ?? '/'));
        foreach (self::PROTECTED_PATH_PREFIXES as $prefix) {
            if (strpos($target_url, $prefix) === 0) {
                throw new RuntimeException('Mutation target is protected: ' . $target_url);
            }
        }

        $payload = $this->payload($mutation);
        foreach (array('selector', 'container_selector', 'target_selector') as $selector_key) {
            if (! empty($payload[$selector_key]) && ! preg_match(self::SELECTOR_PATTERN, (string) $payload[$selector_key])) {
                throw new RuntimeException('Invalid selector: ' . (string) $payload[$selector_key]);
            }
        }
    }

    private function payload(array $mutation): array
    {
        return isset($mutation['payload']) && is_array($mutation['payload']) ? $mutation['payload'] : array();
    }

    private function content_from_payload(array $payload): string
    {
        if (isset($payload['content'])) {
            return wp_kses_post((string) $payload['content']);
        }
        $html = '';
        foreach (($payload['content_blocks'] ?? array()) as $block) {
            if (! is_array($block)) {
                continue;
            }
            $text = trim((string) ($block['text'] ?? ''));
            if ($text === '') {
                continue;
            }
            $type = sanitize_key((string) ($block['type'] ?? 'paragraph'));
            if (in_array($type, array('heading', 'h2'), true)) {
                $html .= '<h2>' . esc_html($text) . '</h2>';
            } else {
                $html .= '<p>' . esc_html($text) . '</p>';
            }
        }
        return wp_kses_post($html);
    }

    private function normalize_url(string $url): string
    {
        $url = trim($url);
        if ($url === '') {
            return '/';
        }
        $parsed = wp_parse_url($url);
        if (isset($parsed['path'])) {
            $url = (string) $parsed['path'];
        }
        return strpos($url, '/') === 0 ? $url : '/' . ltrim($url, '/');
    }

    private function resolve_post_by_url(string $url): WP_Post
    {
        $normalized = $this->normalize_url($url);
        $post_id = url_to_postid(home_url($normalized));
        if (! $post_id) {
            throw new RuntimeException('Unable to resolve page for URL: ' . $normalized);
        }
        $post = get_post($post_id);
        if (! $post instanceof WP_Post) {
            throw new RuntimeException('Resolved post is invalid for URL: ' . $normalized);
        }
        return $post;
    }

    private function snapshot_post_state(int $post_id, bool $include_title, bool $include_description, bool $include_content, bool $include_schema): array
    {
        $state = array('post_id' => $post_id);
        if ($include_title) {
            $state['post_title'] = get_post_field('post_title', $post_id);
            $state['meta_title'] = array(
                '_lsos_meta_title' => get_post_meta($post_id, '_lsos_meta_title', true),
                '_yoast_wpseo_title' => get_post_meta($post_id, '_yoast_wpseo_title', true),
                'rank_math_title' => get_post_meta($post_id, 'rank_math_title', true),
                '_aioseo_title' => get_post_meta($post_id, '_aioseo_title', true),
            );
        }
        if ($include_description) {
            $state['meta_description'] = array(
                '_lsos_meta_description' => get_post_meta($post_id, '_lsos_meta_description', true),
                '_yoast_wpseo_metadesc' => get_post_meta($post_id, '_yoast_wpseo_metadesc', true),
                'rank_math_description' => get_post_meta($post_id, 'rank_math_description', true),
                '_aioseo_description' => get_post_meta($post_id, '_aioseo_description', true),
            );
        }
        if ($include_content) {
            $state['post_content'] = get_post_field('post_content', $post_id);
        }
        if ($include_schema) {
            $state['schema_markup'] = get_post_meta($post_id, '_lsos_schema_markup', true);
        }
        return $state;
    }

    private function post_version(WP_Post $post): array
    {
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
            'content' => (string) $post->post_content,
            'meta_title' => (string) get_post_meta($post->ID, '_lsos_meta_title', true),
            'meta_description' => (string) get_post_meta($post->ID, '_lsos_meta_description', true),
            'canonical' => (string) get_post_meta($post->ID, '_lsos_canonical_url', true),
            'schema' => (string) get_post_meta($post->ID, '_lsos_schema_markup', true),
            'status' => (string) $post->post_status,
        ));
        return array(
            'revision_id' => $revision_id,
            'content_hash' => hash('sha256', (string) $fingerprint),
        );
    }

    private function preview_before_state(WP_Post $post, string $action): array
    {
        switch ($action) {
            case 'update_meta_title':
                return array('value' => $this->first_saved_meta($post->ID, array('_lsos_meta_title', '_yoast_wpseo_title', 'rank_math_title', '_aioseo_title')), 'label' => 'Current search title');
            case 'update_meta_description':
                return array('value' => $this->first_saved_meta($post->ID, array('_lsos_meta_description', '_yoast_wpseo_metadesc', 'rank_math_description', '_aioseo_description')), 'label' => 'Current search description');
            case 'add_schema_markup':
                return array('value' => (string) get_post_meta($post->ID, '_lsos_schema_markup', true), 'label' => 'Current structured data');
            case 'insert_internal_link':
                return array('value' => 'No matching InsightOS link is recorded yet.', 'label' => 'Current page link');
            case 'create_internal_anchor':
                return array('value' => 'No matching InsightOS page anchor is recorded yet.', 'label' => 'Current page anchor');
        }
        return array('value' => '', 'label' => 'Current value');
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

    private function preview_after_state(string $action, array $payload): array
    {
        switch ($action) {
            case 'update_meta_title':
                return array('value' => (string) ($payload['title'] ?? $payload['value'] ?? ''), 'label' => 'New search title');
            case 'update_meta_description':
                return array('value' => (string) ($payload['description'] ?? $payload['value'] ?? ''), 'label' => 'New search description');
            case 'add_schema_markup':
                return array('value' => $payload['schema'] ?? $payload['schema_json'] ?? $payload['value'] ?? array(), 'label' => 'New structured data');
            case 'insert_internal_link':
                return array('value' => array('link_to' => $payload['target_url'] ?? '', 'words' => $payload['anchor_text'] ?? ''), 'label' => 'New page link');
            case 'create_internal_anchor':
                return array('value' => (string) ($payload['anchor_id'] ?? $payload['anchor_slug'] ?? $payload['anchor_text'] ?? ''), 'label' => 'New page anchor');
            case 'publish_content_page':
                return array('value' => array('title' => $payload['title'] ?? '', 'slug' => $payload['slug'] ?? '', 'status' => $payload['status'] ?? $payload['publication_state'] ?? 'draft'), 'label' => 'New draft page');
        }
        return array('value' => $payload, 'label' => 'New value');
    }

    private function build_rollback_payload(string $action, int $post_id, array $before_state, string $source_url = ''): array
    {
        return array(
            'action' => $action,
            'post_id' => $post_id,
            'source_url' => $source_url,
            'before_state' => $before_state,
        );
    }

    private function restore_post_state(int $post_id, array $rollback): void
    {
        $before = isset($rollback['before_state']) && is_array($rollback['before_state']) ? $rollback['before_state'] : array();
        if (array_key_exists('post_title', $before)) {
            wp_update_post(array('ID' => $post_id, 'post_title' => (string) $before['post_title']));
        }
        if (array_key_exists('post_content', $before)) {
            wp_update_post(array('ID' => $post_id, 'post_content' => (string) $before['post_content']));
        }
        if (isset($before['meta_title']) && is_array($before['meta_title'])) {
            foreach ($before['meta_title'] as $key => $value) {
                update_post_meta($post_id, $key, $value);
            }
        }
        if (isset($before['meta_description']) && is_array($before['meta_description'])) {
            foreach ($before['meta_description'] as $key => $value) {
                update_post_meta($post_id, $key, $value);
            }
        }
        if (array_key_exists('schema_markup', $before)) {
            update_post_meta($post_id, '_lsos_schema_markup', $before['schema_markup']);
        }
    }

    private function apply_anchor_in_content(string $content, string $anchor_text, string $target_url, string $selector): string
    {
        if ($content === '' || strpos($content, 'href="' . esc_attr($target_url) . '"') !== false) {
            return $content;
        }

        $dom = $this->load_html_fragment($content);
        $xpath = new DOMXPath($dom);
        foreach ($this->scope_nodes($xpath, $selector) as $scope_node) {
            $text_node = $this->first_text_node_match($xpath, $scope_node, $anchor_text);
            if (! $text_node instanceof DOMText) {
                continue;
            }
            $this->replace_text_with_anchor($dom, $text_node, $anchor_text, $target_url);
            return $this->save_html_fragment($dom);
        }

        return $content;
    }

    private function inject_anchor_id(string $content, string $anchor_id, string $selector): string
    {
        $dom = $this->load_html_fragment($content);
        $xpath = new DOMXPath($dom);
        $duplicate_query = $xpath->query(sprintf('//*[@id="%s"]', esc_attr($anchor_id)));
        if ($duplicate_query instanceof DOMNodeList && $duplicate_query->length > 0) {
            return $content;
        }

        $nodes = $this->scope_nodes($xpath, $selector !== '' ? $selector : 'h2');
        if (empty($nodes)) {
            return $content;
        }
        $node = $nodes[0];
        if ($node instanceof DOMElement) {
            $node->setAttribute('id', $anchor_id);
            return $this->save_html_fragment($dom);
        }

        return $content;
    }

    private function load_html_fragment(string $html): DOMDocument
    {
        $dom = new DOMDocument('1.0', 'UTF-8');
        libxml_use_internal_errors(true);
        $dom->loadHTML('<?xml encoding="utf-8" ?><div id="lsos-root">' . $html . '</div>', LIBXML_HTML_NOIMPLIED | LIBXML_HTML_NODEFDTD);
        libxml_clear_errors();
        return $dom;
    }

    private function save_html_fragment(DOMDocument $dom): string
    {
        $root = $dom->getElementById('lsos-root');
        if (! $root instanceof DOMElement) {
            return '';
        }
        $html = '';
        foreach ($root->childNodes as $child) {
            $html .= $dom->saveHTML($child);
        }
        return $html;
    }

    private function scope_nodes(DOMXPath $xpath, string $selector): array
    {
        $query = $selector === '' ? '//*[@id="lsos-root"]' : $this->selector_to_xpath($selector);
        $nodes = $xpath->query($query);
        return $nodes instanceof DOMNodeList ? iterator_to_array($nodes) : array();
    }

    private function selector_to_xpath(string $selector): string
    {
        $segments = preg_split('/\s+/', trim($selector)) ?: array('*');
        $parts = array();
        foreach ($segments as $segment) {
            $parts[] = $this->selector_segment_to_xpath($segment);
        }
        return '//*[@id="lsos-root"]//' . implode('//', $parts);
    }

    private function selector_segment_to_xpath(string $segment): string
    {
        $tag = '*';
        $predicates = array();
        if (preg_match('/^[a-zA-Z][a-zA-Z0-9_-]*/', $segment, $tag_match)) {
            $tag = $tag_match[0];
        }
        if (preg_match('/#([A-Za-z][A-Za-z0-9_:-]*)/', $segment, $id_match)) {
            $predicates[] = '@id="' . esc_attr($id_match[1]) . '"';
        }
        if (preg_match_all('/\.([A-Za-z][A-Za-z0-9_:-]*)/', $segment, $class_matches)) {
            foreach ($class_matches[1] as $class_name) {
                $predicates[] = 'contains(concat(" ", normalize-space(@class), " "), " ' . esc_attr($class_name) . ' ")';
            }
        }
        return $tag . (! empty($predicates) ? '[' . implode(' and ', $predicates) . ']' : '');
    }

    private function first_text_node_match(DOMXPath $xpath, DOMNode $scope_node, string $needle): ?DOMText
    {
        $text_nodes = $xpath->query('.//text()[normalize-space()]', $scope_node);
        if (! $text_nodes instanceof DOMNodeList) {
            return null;
        }
        foreach ($text_nodes as $text_node) {
            if (! $text_node instanceof DOMText) {
                continue;
            }
            $parent_name = strtolower((string) ($text_node->parentNode?->nodeName ?? ''));
            if (in_array($parent_name, array('a', 'script', 'style', 'noscript'), true)) {
                continue;
            }
            if (mb_stripos($text_node->nodeValue, $needle) !== false) {
                return $text_node;
            }
        }
        return null;
    }

    private function replace_text_with_anchor(DOMDocument $dom, DOMText $text_node, string $anchor_text, string $target_url): void
    {
        $value = $text_node->nodeValue;
        $position = mb_stripos($value, $anchor_text);
        if ($position === false) {
            return;
        }
        $before = mb_substr($value, 0, $position);
        $match = mb_substr($value, $position, mb_strlen($anchor_text));
        $after = mb_substr($value, $position + mb_strlen($anchor_text));
        $fragment = $dom->createDocumentFragment();
        if ($before !== '') {
            $fragment->appendChild($dom->createTextNode($before));
        }
        $anchor = $dom->createElement('a', $match);
        $anchor->setAttribute('href', esc_url_raw($target_url));
        $fragment->appendChild($anchor);
        if ($after !== '') {
            $fragment->appendChild($dom->createTextNode($after));
        }
        $text_node->parentNode->replaceChild($fragment, $text_node);
    }

    private function result(array $mutation, string $status, array $before_state, array $after_state, array $rollback_payload): array
    {
        return array(
            'mutation_id' => (string) ($mutation['mutation_id'] ?? ''),
            'status' => $status,
            'mutation_type' => (string) ($mutation['action'] ?? $mutation['mutation_type'] ?? ''),
            'target_url' => (string) ($mutation['target_url'] ?? ''),
            'before_state' => $before_state,
            'after_state' => $after_state,
            'rollback_payload' => $rollback_payload,
        );
    }
}
