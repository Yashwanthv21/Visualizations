import bar_chart_race as bcr
df = bcr.load_dataset('covid19_tutorial')
bcr.bar_chart_race(df=df,filename="videos/anim1.mp4")
bcr.bar_chart_race(df=df, orientation='v',filename="videos/anim2.mp4")