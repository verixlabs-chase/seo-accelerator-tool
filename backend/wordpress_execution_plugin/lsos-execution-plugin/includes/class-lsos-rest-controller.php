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
        register_rest_route('lsos/v1', '/mutations/apply', array(
            'methods' => WP_REST_Server::CREATABLE,
            'callback' => array($this, 'apply_mutations'),
            'permission_callback' => array($this, 'authorize'),
        ));

        register_rest_route('lsos/v1', '/mutations/rollback', array(
            'methods' => WP_REST_Server::CREATABLE,
            'callback' => array($this, 'rollback_mutations'),
            'permission_callback' => array($this, 'authorize'),
        ));
    }

    public function authorize(WP_REST_Request $request)
    {
        return $this->auth->authorize_request($request);
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
}
