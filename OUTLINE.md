I would like to build an opengl music visualizer, similar to projectM, however I'm going to take a different approach.

- music channel extraction
  - i want to use ai (either openai/claude) or another paid service that specializes in music analysis
  - i would like to extract the different music channels from the audio file
  - i would like to save frequency and amplitude modulation data (i just need data, i don't care about the actual audio)
  - i would like to save this data in a database
  - i would also include the overall track frequency and and amplitude modulation

- music metadata
  - i would like to employ a variety of services to assign metadata that would be helpful
  - fields of interest that already exist in my mp3 files
    - spotify valence/danceability
    - mood
    - context
    - genre
  - mood analysis
    - bridge.audio
    - sonoteller
    - cyanite.ai
    - musiio
    - aims api
  - lyric analysis
    - musixmatch pro
    - lyricsgenius
    - lrclib/lrcget
  - genre analysis:
    - every noise at once
    - chosic music genre finder
    - pitchplus app
    - submithub 'whats my genre'

- music visualization
  - combining the channel data with lyrics and emotional metadata, i would like that to drive the music visualization
  - the first visualizations would be simple bar/line graphs that show the frequency and amplitude modulation of the
    music channels
  - i would then work in the timed lyrics for dynamic lyric display
  - then i would like to start building more advanced shaders:
    - given all the channels data, their maximums and minimums, i would like to build a shader that would show the music  
      channels in a 3d space
    - different visualizations for different channels, like radial graphs for drums and bass, and 2d graphs for vocals
    - different analysis of the channels, individually and together, againt the backdrop of that channels overall data
      should provide the foundation for a variety of different visualizations
  - and finally , incorporating the emotional metadata would allow for the background, energy, and atmosphere of the
    music to be reflected in the visualization
    - would probably keep this simple at first, like static background wallpaper based on the mood and genre
    - visualization scene would endeavor to match the mood, genre, and energy of the music

- eventually i would like to have a large collection of the music metadata, and provide that as a service to the client
  program that would produce the visualizations- would like to incorporate a lot off the good work already done with milk drop, projectm, etc
