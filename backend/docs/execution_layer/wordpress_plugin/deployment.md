# Deployment

1. Copy `wordpress_execution_plugin/lsos-execution-plugin` into `wp-content/plugins/`.
2. Activate the plugin.
3. Set credentials in `wp-config.php`:

```php
define('LSOS_EXECUTION_PLUGIN_TOKEN', '...');
define('LSOS_EXECUTION_PLUGIN_SHARED_SECRET', '...');
```

4. Configure matching `base_url`, `plugin_token`, and `shared_secret` in the LSOS backend provider credentials.
