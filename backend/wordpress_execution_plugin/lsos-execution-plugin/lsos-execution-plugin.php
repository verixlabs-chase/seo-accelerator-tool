<?php
/**
 * Plugin Name: LSOS WordPress Execution Plugin
 * Description: Secure mutation execution engine for the LSOS autonomous SEO platform.
 * Version: 1.0.0
 * Author: Verix Labs
 */

if (! defined('ABSPATH')) {
    exit;
}

define('LSOS_EXECUTION_PLUGIN_VERSION', '1.0.0');
define('LSOS_EXECUTION_PLUGIN_DIR', plugin_dir_path(__FILE__));
define('LSOS_EXECUTION_PLUGIN_URL', plugin_dir_url(__FILE__));

require_once LSOS_EXECUTION_PLUGIN_DIR . 'includes/class-lsos-auth.php';
require_once LSOS_EXECUTION_PLUGIN_DIR . 'includes/class-lsos-audit-store.php';
require_once LSOS_EXECUTION_PLUGIN_DIR . 'includes/class-lsos-dom-mutation-engine.php';
require_once LSOS_EXECUTION_PLUGIN_DIR . 'includes/class-lsos-rest-controller.php';
require_once LSOS_EXECUTION_PLUGIN_DIR . 'includes/class-lsos-execution-plugin.php';

register_activation_hook(__FILE__, array('LSOS_Audit_Store', 'install'));

function lsos_execution_plugin(): LSOS_Execution_Plugin
{
    return LSOS_Execution_Plugin::instance();
}

lsos_execution_plugin();
