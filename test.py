import vlc


def main():
    Instance = vlc.Instance(['--video-on-top'])
    player = Instance.media_player_new()
    player.video_set_mouse_input(False)
    player.video_set_key_input(False)
    player.set_mrl("http://{ip}:8080/stream?topic=/camera_node/image_raw".format(ip='192.168.0.80'), "network-caching=300")
    player.audio_set_mute(True)




if __name__ == '__main__':
    main()