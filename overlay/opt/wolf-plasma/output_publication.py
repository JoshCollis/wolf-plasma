"""Publish a genuinely learned nested mode through KWin's normal config path."""
import json
import subprocess


def publish_current_mode(state, env, width, height, rate):
    attempted = state / 'mode-publication-requested'
    if attempted.exists() or env.get('WAYLAND_DISPLAY') == env.get('WOLF_PLASMA_PARENT_DISPLAY'):
        return False
    query = subprocess.run(['kscreen-doctor', '-j'], env=env, capture_output=True,
                           text=True, timeout=2)
    if query.returncode:
        return False
    try:
        outputs = json.loads(query.stdout)['outputs']
        if len(outputs) != 1:
            return False
        output = outputs[0]
        name = output['name']
        output_id, mode_id = str(output['id']), str(output['currentModeId'])
        # This is the child KWin Wayland backend, never Wolf's HEADLESS output.
        if (output['connected'] is not True or not isinstance(name, str) or not name.startswith('WL-')
                or not name[3:].isascii() or not name[3:].isdecimal()):
            return False
        if not all(value.isascii() and value.isdecimal() for value in (output_id, mode_id)):
            return False
        modes = [mode for mode in output['modes'] if str(mode['id']) == mode_id]
        if len(modes) != 1:
            return False
        mode = modes[0]
        if (mode['size']['width'], mode['size']['height']) != (width, height):
            return False
        if abs(round(float(mode['refreshRate']) * 1000) - rate * 1000) > 500:
            return False
    except (KeyError, TypeError, ValueError, OverflowError):
        return False
    # One startup attempt only. No custom mode, requested rate, scale or layout
    # is set: apply the existing CURRENT mode whose real backend state matches
    # the independently validated parent. Normal Workspace configuration then
    # emits LogicalOutput::currentModeChanged and updates the stale wl_output.
    attempted.touch()
    applied = subprocess.run(['kscreen-doctor', f'output.{output_id}.mode.{mode_id}'],
                             env=env, capture_output=True, text=True, timeout=2)
    if applied.returncode:
        return False
    print('Synchronized native output publication from its existing current backend mode', flush=True)
    return True
