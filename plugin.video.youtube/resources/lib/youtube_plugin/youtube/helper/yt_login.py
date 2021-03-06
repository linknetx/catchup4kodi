__author__ = 'bromix'

import time
from ...youtube.youtube_exceptions import LoginException


def process(mode, provider, context, re_match, sign_out_refresh=True):
    def _do_logout():
        # we clear the cache, so none cached data of an old account will be displayed.
        context.get_function_cache().clear()

        signout_access_manager = context.get_access_manager()
        if signout_access_manager.has_refresh_token():
            refresh_tokens = signout_access_manager.get_refresh_token().split('|')
            refresh_tokens = list(set(refresh_tokens))
            for _refresh_token in refresh_tokens:
                provider.get_client(context).revoke(_refresh_token)
        provider.reset_client()
        signout_access_manager.update_access_token(access_token='', refresh_token='')

    def _do_login(_for_tv=False):
        _client = provider.get_client(context)
        try:
            if _for_tv:
                json_data = _client.request_device_and_user_code_tv()
            else:
                json_data = _client.request_device_and_user_code()
        except LoginException:
            _do_logout()
            raise
        interval = int(json_data.get('interval', 5)) * 1000
        if interval > 60000:
            interval = 5000
        device_code = json_data['device_code']
        user_code = json_data['user_code']

        text = context.localize(provider.LOCAL_MAP['youtube.sign.go_to']) % '[B]youtube.com/activate[/B]'
        text += '[CR]%s [B]%s[/B]' % (context.localize(provider.LOCAL_MAP['youtube.sign.enter_code']), user_code)
        dialog = context.get_ui().create_progress_dialog(
            heading=context.localize(provider.LOCAL_MAP['youtube.sign.in']), text=text, background=False)

        steps = (10 * 60 * 1000) / interval  # 10 Minutes
        dialog.set_total(steps)
        for i in range(steps):
            dialog.update()
            try:
                if _for_tv:
                    json_data = _client.request_access_token_tv(device_code)
                else:
                    json_data = _client.request_access_token(device_code)
            except LoginException:
                _do_logout()
                raise
            if not 'error' in json_data:
                _access_token = json_data.get('access_token', '')
                _expires_in = time.time() + int(json_data.get('expires_in', 3600))
                _refresh_token = json_data.get('refresh_token', '')
                if _access_token and _refresh_token:
                    dialog.close()
                    return _access_token, _expires_in, _refresh_token

            elif json_data['error'] != u'authorization_pending':
                message = json_data['error']
                title = '%s: %s' % (context.get_name(), message)
                context.get_ui().show_notification(message, title)
                context.log_error('Error: |%s|' % message)

            if dialog.is_aborted():
                dialog.close()
                return '', 0, ''

            context.sleep(interval)
        dialog.close()

    if mode == 'out':
        _do_logout()
        if sign_out_refresh:
            context.get_ui().refresh_container()
    elif mode == 'in':
        context.get_ui().on_ok(context.localize(provider.LOCAL_MAP['youtube.sign.twice.title']),
                               context.localize(provider.LOCAL_MAP['youtube.sign.twice.text']))

        access_token_tv, expires_in_tv, refresh_token_tv = _do_login(_for_tv=True)
        # abort tv login
        context.log_debug('YouTube-TV Login: Access Token |%s| Refresh Token |%s| Expires |%s|' % (access_token_tv != '', refresh_token_tv != '', expires_in_tv))
        if not access_token_tv and not refresh_token_tv:
            provider.reset_client()
            context.get_access_manager().update_access_token('')
            context.get_ui().refresh_container()
            return

        access_token_kodi, expires_in_kodi, refresh_token_kodi = _do_login(_for_tv=False)
        # abort kodi login
        context.log_debug('YouTube-Kodi Login: Access Token |%s| Refresh Token |%s| Expires |%s|' % (access_token_kodi != '', refresh_token_kodi != '', expires_in_kodi))
        if not access_token_kodi and not refresh_token_kodi:
            provider.reset_client()
            context.get_access_manager().update_access_token('')
            context.get_ui().refresh_container()
            return

        access_token = '%s|%s' % (access_token_tv, access_token_kodi)
        refresh_token = '%s|%s' % (refresh_token_tv, refresh_token_kodi)
        expires_in = min(expires_in_tv, expires_in_kodi)

        # we clear the cache, so none cached data of an old account will be displayed.
        context.get_function_cache().clear()

        major_version = context.get_system_version().get_version()[0]
        context.get_settings().set_int('youtube.login.version', major_version)

        provider.reset_client()
        context.get_access_manager().update_access_token(access_token, expires_in, refresh_token)
        context.get_ui().refresh_container()
