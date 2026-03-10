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
        $target_url = $this->normalize_url((string) $mutation['target_url']);
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
        $schema = $payload['schema'] ?? $payload['value'] ?? null;
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
                'post_status' => sanitize_key((string) ($payload['status'] ?? 'draft')),
                'post_title' => $title,
                'post_content' => wp_kses_post((string) ($payload['content'] ?? '')),
                'post_name' => sanitize_title((string) ($payload['slug'] ?? $title)),
            ),
            true
        );
        if (is_wp_error($post_id)) {
            throw new RuntimeException($post_id->get_error_message());
        }

        if (! empty($payload['meta_title'])) {
            update_post_meta($post_id, '_lsos_meta_title', sanitize_text_field((string) $payload['meta_title']));
        }
        if (! empty($payload['meta_description'])) {
            update_post_meta($post_id, '_lsos_meta_description', sanitize_textarea_field((string) $payload['meta_description']));
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
