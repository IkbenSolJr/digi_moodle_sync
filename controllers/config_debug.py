def _get_moodle_config(self):
    """Get Moodle configuration with correct parameter names"""
    params = request.env['ir.config_parameter'].sudo()
    
    # Get parameters with correct names from your system
    token = params.get_param('digi_moodle_sync.token')
    url = params.get_param('digi_moodle_sync.moodle_url')
    
    # Clean URL (remove trailing slash)
    if url:
        url = url.rstrip('/')
    
    # Log for debugging
    _logger.info(f"Moodle Config - Token: {'Found' if token else 'Missing'}, URL: {'Found' if url else 'Missing'}")
    
    return {
        'token': token,
        'url': url
    }