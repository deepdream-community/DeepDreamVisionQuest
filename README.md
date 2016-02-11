# DeepDream Vision Quest
Continuous Deep Dream processing of webcam input

This script runs the Deep Dream neural visualization on camera input to produce live output. Its a magic mirror that reveals alien vistas within the surrounding environment. Deep Dream Vision Quest is the subject of my GDC 2016 Poster Session, details found here:

[Find Your Spirit Animal In A Deep Dream Vision Quest](http://schedule.gdconf.com/session/find-your-spirit-animal-in-a-deep-dream-vision-quest)

Neural visualization is computationally intensive and the Caffe/OpenCV/CUDA stack was designed to optimize training and learning, not so much though for real time output of neural visualization. Even with a fast GPU (I'm running a TITAN X), lower resolution and reduced iteration rates, 30fps output isn't likely. This was a huge disappointment at first. The realtime desktop DMT simulator I'd imagined will have to wait.


The script captures a video frame and will dream about that frame indefinitely, passing the output of the last cycle as the input of the next cycle, zooming in slightly each time. The real world soon disappears.

Requirements
-------------
Python
Caffe (and other deepdream dependencies)
FFMPEG
CV2 (if you use optical flow)

Credits
-------------
Gary Boodhoo | sciencefictionthriller.com | @skinjester




