def _filesystem_root_for_audio(audio_root_setting: str) -> str:
    """Convert path setting to absolute path, with '..' relative to project root"""
    if '..' in audio_root_setting:
        # Convert .. to absolute path relative to project root 
        from pathlib import Path
        return str(Path(__file__).parent.parent.parent / audio_root_setting.replace('..', ''))
    return audio_root_setting
