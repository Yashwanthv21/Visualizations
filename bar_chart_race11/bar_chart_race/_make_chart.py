import warnings

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from matplotlib import ticker, colors

from ._utils import prepare_wide_data

from matplotlib.offsetbox import TextArea, DrawingArea, OffsetImage, AnnotationBbox
import matplotlib.image as mpimg
import cv2

class _BarChartRace:
    
    def __init__(self, df, filename, orientation, sort, n_bars, fixed_order, fixed_max,
                 steps_per_period, period_length, interpolate_period, bar_label_position, 
                 bar_label_fmt, bar_size, period_label, period_fmt, period_summary_func, 
                 perpendicular_bar_func, figsize, cmap, title, bar_label_size, 
                 tick_label_size, shared_fontdict, scale, writer, fig, dpi, bar_kwargs, 
                 filter_column_colors):
        self.filename = filename
        self.extension = self.get_extension()
        self.orientation = orientation
        self.sort = sort
        self.n_bars = n_bars or df.shape[1]
        self.fixed_order = fixed_order
        self.fixed_max = fixed_max
        self.steps_per_period = steps_per_period
        self.interpolate_period = interpolate_period
        self.bar_label_position = bar_label_position
        self.bar_label_fmt = bar_label_fmt
        self.bar_size = bar_size
        self.period_label = self.get_period_label(period_label)
        self.period_fmt = period_fmt
        self.period_summary_func = period_summary_func
        self.perpendicular_bar_func = perpendicular_bar_func
        self.period_length = period_length
        self.figsize = figsize
        self.title = self.get_title(title)
        self.bar_label_size = bar_label_size
        self.tick_label_size = tick_label_size
        self.orig_rcParams = self.set_shared_fontdict(shared_fontdict)
        self.scale = scale
        self.writer = self.get_writer(writer)
        self.dpi = dpi
        self.fps = 1000 / self.period_length * steps_per_period
        self.filter_column_colors = filter_column_colors
        self.extra_pixels = 0
        
        self.validate_params()
        self.bar_kwargs = self.get_bar_kwargs(bar_kwargs)
        self.html = self.filename is None
        self.df_values, self.df_ranks = self.prepare_data(df)
        self.col_filt = self.get_col_filt()
        self.bar_colors = self.get_bar_colors(cmap)
        self.str_index = self.df_values.index.astype('str')
        self.subplots_adjust = self.get_subplots_adjust()
        self.fig = self.get_fig(fig)
        

    def get_extension(self):
        if self.filename:
            return self.filename.split('.')[-1]

    def validate_params(self):
        if isinstance(self.filename, str):
            if '.' not in self.filename:
                raise ValueError('`filename` must have an extension')
        elif self.filename is not None:
            raise TypeError('`filename` must be None or a string')
            
        if self.sort not in ('asc', 'desc'):
            raise ValueError('`sort` must be "asc" or "desc"')

        if self.orientation not in ('h', 'v'):
            raise ValueError('`orientation` must be "h" or "v"')

        if self.bar_label_position not in ('outside', 'inside', None):
            raise ValueError('`bar_label_position` must be one of "outside", "inside" or None')

    def get_bar_kwargs(self, bar_kwargs):
        bar_kwargs = bar_kwargs or {}
        if 'width' in bar_kwargs or 'height' in bar_kwargs:
            raise ValueError("Do not set the width or height with `bar_kwargs`. "
                             "Instead, use `bar_size`.")
        if self.orientation == 'h':
            bar_kwargs['height'] = self.bar_size
        else:
            bar_kwargs['width'] = self.bar_size
        if 'alpha' not in bar_kwargs:
            bar_kwargs['alpha'] = .8
        if 'ec' not in bar_kwargs:
            bar_kwargs['ec'] = 'white'
        return bar_kwargs

    def get_period_label(self, period_label):
        if period_label is False:
            return False

        default_period_label = {'size': 12}
        if self.orientation == 'h':
            default_period_label['x'] = .95
            default_period_label['y'] = .15 if self.sort == 'desc' else .85
            default_period_label['ha'] = 'right'
            default_period_label['va'] = 'center'
        else:
            default_period_label['x'] = .95 if self.sort == 'desc' else .05
            default_period_label['y'] = .85
            default_period_label['ha'] = 'right' if self.sort == 'desc' else 'left'
            default_period_label['va'] = 'center'

        if period_label is True:
            return default_period_label
        elif isinstance(period_label, dict):
            period_label = {**default_period_label, **period_label}
        else:
            raise TypeError('`period_label` must be a boolean or dictionary')

        return period_label

    def get_title(self, title):
        if isinstance(title, str):
            return {'label': title}
        elif isinstance(title, dict):
            if 'label' not in title:
                raise ValueError('You must use the key "label" in the `title` dictionary '
                                 'to supply the name of the title')
        elif title is not None:
            raise TypeError('`title` must be either a string or dictionary')
        else:
            return {'label': None}
        return title

    def set_shared_fontdict(self, shared_fontdict):
        orig_rcParams = plt.rcParams.copy()
        if shared_fontdict is None:
            return orig_rcParams
        for k, v in shared_fontdict.items():
            if k not in ['fontsize', 'size']:
                if k in ['cursive', 'family', 'fantasy', 'monospace', 'sans-serif', 'serif']:
                        if isinstance(v, str):
                            v = [v]
                if k == 'color':
                    plt.rcParams['text.color'] = v
                    plt.rcParams['xtick.color'] = v
                    plt.rcParams['ytick.color'] = v
                    continue
                try:
                    plt.rcParams[f'font.{k}'] = v
                except KeyError:
                    raise KeyError(f"{k} is not a valid key in `sharedfont_dict`"
                                    "It must be one of "
                                    "'cursive', 'family', 'fantasy', 'monospace',"
                                    "sans-serif', 'serif',"
                                    "'stretch', 'style', 'variant', 'weight'")
        return orig_rcParams

    def get_writer(self, writer):
        if writer is None:
            if self.extension == 'gif':
                writer = 'imagemagick'
            elif self.extension == 'html':
                writer = 'html'
            else:
                writer = plt.rcParams['animation.writer']
        return writer

    def prepare_data(self, df):
        if self.fixed_order is True:
            last_values = df.iloc[-1].sort_values(ascending=False)
            cols = last_values.iloc[:self.n_bars].index
            df = df[cols]
        elif isinstance(self.fixed_order, list):
            cols = self.fixed_order
            df = df[cols]
            self.n_bars = min(len(cols), self.n_bars)
            
        compute_ranks = self.fixed_order is False
        dfs = prepare_wide_data(df, self.orientation, self.sort, self.n_bars,
                                self.interpolate_period, self.steps_per_period,
                                compute_ranks)
        if isinstance(dfs, tuple):
            df_values, df_ranks = dfs
        else:
            df_values = dfs

        if self.fixed_order:
            n = df_values.shape[1] + 1
            m = df_values.shape[0]
            rank_row = np.arange(1, n)
            if (self.sort == 'desc' and self.orientation == 'h') or \
                (self.sort == 'asc' and self.orientation == 'v'):
                rank_row = rank_row[::-1]
            
            ranks_arr = np.repeat(rank_row.reshape(1, -1), m, axis=0)
            df_ranks = pd.DataFrame(data=ranks_arr, columns=cols)

        return df_values, df_ranks
        
    def get_col_filt(self):
        col_filt = pd.Series([True] * self.df_values.shape[1])
        if self.n_bars < self.df_ranks.shape[1]:
            orient_sort = self.orientation, self.sort
            if orient_sort in [('h', 'asc'), ('v', 'desc')]:
                # 1 is high
                col_filt = (self.df_ranks < self.n_bars + .99).any()
            else:
                # 1 is low
                col_filt = (self.df_ranks > 0).any()

            if self.filter_column_colors and not col_filt.all():
                self.df_values = self.df_values.loc[:, col_filt]
                self.df_ranks = self.df_ranks.loc[:, col_filt]
        return col_filt
        
    def get_bar_colors(self, cmap):
        if cmap is None:
            cmap = 'dark12'
            if self.df_values.shape[1] > 10:
                cmap = 'dark24'
            
        if isinstance(cmap, str):
            from ._colormaps import colormaps
            try:
                bar_colors = colormaps[cmap.lower()]
            except KeyError:
                raise KeyError(f'Colormap {cmap} does not exist. Here are the '
                               f'possible colormaps: {colormaps.keys()}')
        elif isinstance(cmap, colors.Colormap):
            bar_colors = cmap(range(cmap.N)).tolist()
        elif isinstance(cmap, list):
            bar_colors = cmap
        elif isinstance(cmap, tuple):
            bar_colors = list(cmap)
        elif hasattr(cmap, 'tolist'):
            bar_colors = cmap.tolist()
        else:
            raise TypeError('`cmap` must be a string name of a colormap, a matplotlib colormap '
                            'instance, list, or tuple of colors')

        # bar_colors is now a list
        n = len(bar_colors)
        orig_bar_colors = bar_colors
        if self.df_values.shape[1] > n:
            bar_colors = bar_colors * (self.df_values.shape[1] // n + 1)
        bar_colors = np.array(bar_colors[:self.df_values.shape[1]])

        if not self.filter_column_colors:
            if not self.col_filt.all():
                col_idx = np.where(self.col_filt)[0] % n
                col_idx_ct = np.bincount(col_idx, minlength=n)
                num_cols = max(self.col_filt.sum(), n)
                exp_ct = np.bincount(np.arange(num_cols) % n, minlength=n)
                if (col_idx_ct > exp_ct).any():
                    warnings.warn("Some of your columns never make an appearance in the animation. "
                                    "To reduce color repetition, set `filter_column_colors` to `True`")
        return bar_colors

    def get_max_plotted_value(self):
        plotted_values = []
        for i in range(len(self.df_values)):
            _, bar_length, _, _ = self.get_bar_info(i)
            plotted_values.append(max(bar_length))
        return max(plotted_values)

    def prepare_axes(self, ax):
        value_axis = ax.xaxis if self.orientation == 'h' else ax.yaxis
        value_axis.grid(True, color='white')
        value_axis.set_major_formatter(ticker.StrMethodFormatter('{x:,.0f}'))
        ax.tick_params(labelsize=self.tick_label_size, length=0, pad=2)
        ax.minorticks_off()
        ax.set_axisbelow(True)
        ax.set_facecolor('.9')
        ax.set_title(**self.title)
        min_val = 1 if self.scale == 'log' else 0

        for spine in ax.spines.values():
            spine.set_visible(False)

        limit = (.2, self.n_bars + .8)
        if self.orientation == 'h':
            ax.set_ylim(limit)
            ax.set_xscale(self.scale)
        else:
            ax.set_xlim(limit)
            ax.set_yscale(self.scale)
            ax.tick_params(axis='x', labelrotation=30)

    def get_subplots_adjust(self):
        import io
        fig = plt.Figure(figsize=self.figsize, dpi=self.dpi)
        ax = fig.add_subplot()
        plot_func = ax.barh if self.orientation == 'h' else ax.bar
        bar_location, bar_length, cols, _ = self.get_bar_info(-1)
        plot_func(bar_location, bar_length, tick_label=cols)
                
        self.prepare_axes(ax)
        texts = self.add_bar_labels(ax, bar_location, bar_length)

        min_val = 1 if self.scale == 'log' else 0
        fig.canvas.print_figure(io.BytesIO(), format='png')
        xmin = min(label.get_window_extent().x0 for label in ax.get_yticklabels()) 
        xmin /= (self.dpi * fig.get_figwidth())
        left = ax.get_position().x0 - xmin + .01

        ymin = min(label.get_window_extent().y0 for label in ax.get_xticklabels()) 
        ymin /= (self.dpi * fig.get_figheight())
        bottom = ax.get_position().y0 - ymin + .01

        if self.fixed_max:
            if self.orientation == 'h':
                self.fixed_max_value = ax.get_xlim()[1]
            else:
                self.fixed_max_value = ax.get_ylim()[1]

        if self.bar_label_position == 'outside':
            max_bar = max(bar_length)
            if self.orientation == 'h':
                max_bar_pixels = ax.transData.transform((max_bar, 0))[0]
                max_text = max(text.get_window_extent().x1 for text in texts)
            else:
                max_bar_pixels = ax.transData.transform((0, max_bar))[1]
                max_text = max(text.get_window_extent().y1 for text in texts)
            
            self.extra_pixels = max_text - max_bar_pixels + 10

            if self.fixed_max:
                end_pixel = max_bar_pixels + self.extra_pixels
                if self.orientation == 'h':
                    self.fixed_max_value = ax.transData.inverted().transform((end_pixel, 0))[0]
                else:
                    self.fixed_max_value = ax.transData.inverted().transform((0, end_pixel))[1]
        return left, bottom

    def fix_axis_limits(self, ax):
        if self.scale == 'log':
            if self.orientation == 'h':
                ax.set_xlim(1)
            else:
                ax.set_ylim(1)

        if self.fixed_max:
            if self.orientation == 'h':
                ax.set_xlim(None, self.fixed_max_value)
            else:
                ax.set_ylim(None, self.fixed_max_value)

    def get_fig(self, fig):
        if fig is not None and not isinstance(fig, plt.Figure):
            raise TypeError('`fig` must be a matplotlib Figure instance')
        if fig is not None:
            if not fig.axes:
                raise ValueError('The figure passed to `fig` must have an axes')
            ax = fig.axes[0]
            self.figsize = fig.get_size_inches()
        else:
            fig = self.create_figure()
        return fig

    def create_figure(self):
        fig = plt.Figure(figsize=self.figsize, dpi=self.dpi)
        ax = fig.add_subplot()
        left, bottom = self.subplots_adjust
        fig.subplots_adjust(left=left, bottom=bottom)
        self.prepare_axes(ax)
        self.fix_axis_limits(ax)
        return fig

    def get_bar_info(self, i):
        bar_location = self.df_ranks.iloc[i].values
        top_filt = (bar_location > 0) & (bar_location < self.n_bars + 1)
        bar_location = bar_location[top_filt]
        bar_length = self.df_values.iloc[i].values[top_filt]
        cols = self.df_values.columns[top_filt]
        colors = self.bar_colors[top_filt]
        return bar_location, bar_length, cols, colors

    def plot_bars(self, ax, i):
        bar_location, bar_length, cols, colors = self.get_bar_info(i)
        # print(bar_location, '#',bar_length, '#',i)
        if self.orientation == 'h':
            ax.barh(bar_location, bar_length, tick_label=cols, 
                    color=colors, **self.bar_kwargs)
            if not self.fixed_max and self.bar_label_position == 'outside':
                max_bar = bar_length.max()
                new_max_pixels = ax.transData.transform((max_bar, 0))[0] + self.extra_pixels
                new_xmax = ax.transData.inverted().transform((new_max_pixels, 0))[0]
                ax.set_xlim(ax.get_xlim()[0], new_xmax)
        else:
            ax.bar(bar_location, bar_length, tick_label=cols, 
                   color=colors, **self.bar_kwargs)
            ax.set_xticklabels(ax.get_xticklabels(), ha='right')
            if not self.fixed_max and self.bar_label_position == 'outside':
                max_bar = bar_length.max()
                new_max_pixels = ax.transData.transform((0, max_bar))[1] + self.extra_pixels
                new_ymax = ax.transData.inverted().transform((0, new_max_pixels))[1]
                ax.set_ylim(ax.get_ylim()[0], new_ymax)
            
        self.add_period_label(ax, i)
        self.add_period_summary(ax, i)
        self.add_bar_labels(ax, bar_location, bar_length)
        self.add_perpendicular_bar(ax, bar_length, i)

    def add_period_label(self, ax, i):
        if self.period_label:
            if self.period_fmt:
                idx_val = self.df_values.index[i]
                if self.df_values.index.dtype.kind == 'M':
                    s = idx_val.strftime(self.period_fmt)
                else:
                    s = self.period_fmt.format(x=idx_val)
            else:
                s = self.str_index[i]

            if len(ax.texts) == 0:
                # first frame
                ax.text(s=s, transform=ax.transAxes, **self.period_label)
            else:
                ax.texts[0].set_text(s)

    def add_period_summary(self, ax, i):
        if self.period_summary_func:
            values = self.df_values.iloc[i]
            ranks = self.df_ranks.iloc[i]
            text_dict = self.period_summary_func(values, ranks)
            if 'x' not in text_dict or 'y' not in text_dict or 's' not in text_dict:
                name = self.period_summary_func.__name__
                raise ValueError(f'The dictionary returned from `{name}` must contain '
                                  '"x", "y", and "s"')
            ax.text(transform=ax.transAxes, **text_dict)

    def add_bar_labels(self, ax, bar_location, bar_length):
        if self.bar_label_position:
            if self.orientation == 'h':
                zipped = zip(bar_length, bar_location)
            else:
                zipped = zip(bar_location, bar_length)
            
            # print(list(zipped))
            # arr_logo = mpimg.imread('logo.png')
            arr_logo = cv2.imread('logo.jpg')
            width = arr_logo.shape[1]
            arr_logo = cv2.resize(arr_logo, dsize=(250, 250), interpolation=cv2.INTER_CUBIC)
            imagebox = OffsetImage(arr_logo, zoom=0.1/3)
            dx = max(bar_length)/200 + arr_logo.shape[1]                 


            if self.orientation == 'h':
                rotation = 0
                ha = 'left'
                va = 'center'
                delta = .01
                if self.bar_label_position == 'inside':
                    delta = -.01
                    ha = 'right'
            else:
                rotation = 90
                ha = 'center'
                va = 'bottom'
                delta = .01
                if self.bar_label_position == 'inside':
                    delta = -.01
                    va = 'top'

            text_objs = []
            for x1, y1 in zipped:
                xtext, ytext = ax.transLimits.transform((x1, y1))
                ximg, yimg = xtext, ytext
                if self.orientation == 'h':
                    xtext += delta 
                    val = x1

                    ximg += (2 * delta)
                    xtext = ximg + (2 * delta)
                else:
                    ytext += delta 
                    val = y1

                    yimg += (2 * delta)
                    ytext = yimg + (2 * delta)

                if callable(self.bar_label_fmt):
                    text = self.bar_label_fmt(val)
                else:
                    text = self.bar_label_fmt.format(x=val)

                # print(xtext, ytext)
                ximg, yimg = ax.transLimits.inverted().transform((ximg, yimg))
                ax.add_artist(AnnotationBbox(imagebox, (ximg + width, yimg),bboxprops =dict(edgecolor=[1,1,1])))           

                xtext, ytext = ax.transLimits.inverted().transform((xtext, ytext))
                text_obj = ax.text(xtext + width, ytext, text, ha=ha, rotation=rotation, 
                                   fontsize=self.bar_label_size, va=va, clip_on=True)
                text_objs.append(text_obj)
            return text_objs

    def add_perpendicular_bar(self, ax, bar_length, i):
        if self.perpendicular_bar_func:
            if isinstance(self.perpendicular_bar_func, str):
                val = pd.Series(bar_length).agg(self.perpendicular_bar_func)
            else:
                values = self.df_values.iloc[i]
                ranks = self.df_ranks.iloc[i]
                val = self.perpendicular_bar_func(values, ranks)

            if not ax.lines:
                if self.orientation == 'h':
                    ax.axvline(val, lw=10, color='.5', zorder=.5)
                else:
                    ax.axhline(val, lw=10, color='.5', zorder=.5)
            else:
                line = ax.lines[0]
                if self.orientation == 'h':
                    line.set_xdata([val] * 2)
                else:
                    line.set_ydata([val] * 2)
            
    def anim_func(self, i):
        ax = self.fig.axes[0]
        for bar in ax.containers:
            bar.remove()
        for artist in ax.artists:
            artist.remove()
        start = int(bool(self.period_label))
        for text in ax.texts[start:]:
            text.remove()
        self.plot_bars(ax, i)
        
    def make_animation(self):
        def init_func():
            ax = self.fig.axes[0]
            self.plot_bars(ax, 0)
        
        interval = self.period_length / self.steps_per_period
        anim = FuncAnimation(self.fig, self.anim_func, range(len(self.df_values)), 
                             init_func, interval=interval)

        try:
            if self.html:
                ret_val = anim.to_html5_video()
                try:
                    from IPython.display import HTML
                    ret_val = HTML(ret_val)
                except ImportError:
                    pass
            else:
                ret_val = anim.save(self.filename, fps=self.fps, writer=self.writer)
        except Exception as e:
            message = str(e)
            raise Exception(message)
        finally:
            plt.rcParams = self.orig_rcParams

        return ret_val


def bar_chart_race(df, filename=None, orientation='h', sort='desc', n_bars=None, 
                   fixed_order=False, fixed_max=False, steps_per_period=10, 
                   period_length=500, interpolate_period=False, 
                   bar_label_position='outside', bar_label_fmt='{x:,.0f}',
                   bar_size=.95, period_label=True, period_fmt=None, 
                   period_summary_func=None, perpendicular_bar_func=None, figsize=(6, 3.5),
                   cmap=None, title=None, bar_label_size=7, 
                   tick_label_size=7, shared_fontdict=None, scale='linear', writer=None, 
                   fig=None, dpi=144, bar_kwargs=None, filter_column_colors=False):
    '''
    Create an animated bar chart race using matplotlib. Data must be in 
    'wide' format where each row represents a single time period and each 
    column represents a distinct category. Optionally, the index can label 
    the time period.

    Bar length and location change linearly from one time period to the next.

    If no `filename` is given, an HTML string is returned, otherwise the 
    animation is saved to disk.

    You must have ffmpeg installed on your machine to save files to disk.
    Get ffmpeg here: https://www.ffmpeg.org/download.html

    To save .gif files you'll need to install ImageMagick.

    This is resource intensive - start with just a few rows of data to test.


    Parameters
    ----------
    df : pandas DataFrame
        Must be a 'wide' DataFrame where each row represents a single period 
        of time. Each column contains the values of the bars for that 
        category. Optionally, use the index to label each time period.
        The index can be of any type.

    filename : `None` or str, default None
        If `None` return animation as an HTML5 string.
        If a string, save animation to that filename location. 
        Use .mp4, .gif, .html, .mpeg, .mov and any other extensions supported
        by ffmpeg or ImageMagick.

    orientation : 'h' or 'v', default 'h'
        Bar orientation - horizontal or vertical

    sort : 'desc' or 'asc', default 'desc'
        Sorts the bars. Use 'desc' to place largest bars on top/left 
        and 'asc' to place largest bars on bottom/right.

    n_bars : int, default None
        Choose the maximum number of bars to display on the graph. 
        By default, use all bars. New bars entering the race will appear 
        from the edge of the axes.

    fixed_order : bool or list, default False
        When `False`, bar order changes every time period to correspond 
        with `sort`. When `True`, bars remained fixed according to their 
        final value corresponding with `sort`. Otherwise, provide a list 
        of the exact order of the categories for the entire duration.

    fixed_max : bool, default False
        Whether to fix the maximum value of the axis containing the values.
        When `False`, the axis for the values will have its maximum (xlim/ylim)
        just after the largest bar of the current time period. 
        The axis maximum will change along with the data.

        When True, the maximum axis value will remain constant for the 
        duration of the animation. For example, in a horizontal bar chart, 
        if the largest bar has a value of 100 for the first time period and 
        10,000 for the last time period. The xlim maximum will be 10,000 
        for each frame.

    steps_per_period : int, default 10
        The number of steps to go from one time period to the next. 
        The bars will grow linearly between each period.

    period_length : int, default 500
        Number of milliseconds to animate each period (row). 
        Default is 500ms (half of a second)

    interpolate_period : bool, default `False`
        Whether to interpolate the period. Only valid for datetime or
        numeric indexes. When set to `True`, for example, 
        the two consecutive periods 2020-03-29 and 2020-03-30 with 
        `steps_per_period` set to 4 would yield a new index of
        2020-03-29 00:00:00
        2020-03-29 06:00:00
        2020-03-29 12:00:00
        2020-03-29 18:00:00
        2020-03-30 00:00:00

    bar_label_position : 'outside', 'inside', or None - default 'outside'
        Position where bar label will be placed. Use None when 
        no label is desired.
    
    bar_label_fmt : str or function, default '{x:,.0f}'
        A new-style formatted string to control the formatting
        of the bar labels. Use `x` as the variable name.

        Provide a function that accepts one numeric argument,
        the value of the bar and returns a string

        Example:
        def func(val):
            new_val = int(round(val, -3))
            return f'{new_val:,.0f}'

    bar_size : float, default .95
        Height/width of bars for horizontal/vertical bar charts. 
        Use a number between 0 and 1
        Represents the fraction of space that each bar takes up. 
        When equal to 1, no gap remains between the bars.

    period_label : bool or dict, default `True`
        If `True` or dict, use the index as a large text label
        on the axes whose value changes each frame. If `False`,
        don't place label on axes.

        Use a dictionary to supply any valid parameters of the 
        matplotlib `text` method.

        Example:
        {
            'x': .99,
            'y': .8,
            'ha': 'right',
            'va': 'center',
            'size': 8
        }

        The default location depends on `orientation` and `sort`; 
        x and y are in axes units
        * h, desc -> x=.95, y=.15, ha='right', va='center'
        * h, asc -> x=.95, y=.85, ha='right', va='center'
        * v, desc -> x=.95, y=.85, ha='right', va='center'
        * v, asc -> x=.05, y=.85, ha='left', va='center'

    period_fmt : str, default `None`
        Either a string with date directives or 
        a new-style (Python 3.6+) formatted string

        For a string with a date directive, find the complete list here
        https://docs.python.org/3/library/datetime.html#strftime-and-strptime-format-codes
        
        Example of string with date directives
            '%B %d, %Y'
        Will change 2020/03/29 to March 29, 2020
        
        For new-style formatted string. Use curly braces and the variable `x`, 
        which will be passed the current period's index value.
        Example:
            'Period {x:10.2f}'

        Date directives will only be used for datetime indexes.

    period_summary_func : function, default None
        Custom text added to the axes each period.
        Create a user-defined function that accepts two pandas Series of the 
        current time period's values and ranks. It must return a dictionary 
        containing at a minimum the keys "x", "y", and "s" which will be 
        passed to the matplotlib `text` method.

        Example:
        def func(values, ranks):
            total = values.sum()
            s = f'Worldwide deaths: {total}'
            return {'x': .85, 'y': .2, 's': s, 'ha': 'right', 'size': 11}

    perpendicular_bar_func : function or str, default None
        Creates a single bar perpendicular to the main bars that spans the 
        length of the axis. 
        
        Use either a string that the DataFrame `agg` method understands or a 
        user-defined function.
            
        DataFrame strings - 'mean', 'median', 'max', 'min', etc..

        The function is passed two pandas Series of the current time period's
        data and ranks. It must return a single value.

        def func(values, ranks):
            return values.quantile(.75)

    figsize : two-item tuple of numbers, default (6, 3.5)
        matplotlib figure size in inches. Will be overridden if figure 
        supplied to `fig`.

    cmap : str, matplotlib colormap instance, or list of colors, default 'dark12'
        Colors to be used for the bars. All matplotlib and plotly 
        colormaps are available by string name. Colors will repeat 
        if there are more bars than colors.

        'dark12' is a discrete colormap. If there are more than 12 columns, 
        then the default colormap will be 'dark24'

        Append "_r" to the colormap name to use the reverse of the colormap.
        i.e. "dark12_r"

    title : str or dict, default None
        Title of plot as a string.
        Use a dictionary to supply several title parameters. You must use the
        key 'label' for the title.
        
        Example:
        {
            'label': 'My Bar Chart Race Title',
            'size': 18,
            'color': 'red',
            'loc': 'right',
            'pad': 12
        }

    bar_label_size : number or str, default 7
        Size in points or relative size str of numeric labels 
        just outside of the bars. See Font Help below.

    tick_label_size : number or str, default 7
        Size in points of tick labels. See Font Help below. 
        See Font Help below

    shared_fontdict : dict, default None
        Dictionary of font properties shared across the tick labels, 
        bar labels, period labels, and title. The only property not shared 
        is `size`. It will be ignored if you try to set it.

        Possible keys are:
            'family', 'weight', 'color', 'style', 'stretch', 'weight', 'variant'
        Here is an example dictionary:
        {
            'family' : 'Helvetica',
            'weight' : 'bold',
            'color' : 'rebeccapurple'
        }

    scale : 'linear' or 'log', default 'linear'
        Type of scaling to use for the axis containing the values

    writer : str or matplotlib Writer instance
        This argument is passed to the matplotlib FuncAnimation.save method.

        By default, the writer will be 'ffmpeg' unless creating a gif,
        then it will be 'imagemagick', or an html file, then it 
        will be 'html'. 
            
        Find all of the availabe Writers:
        >>> from matplotlib import animation
        >>> animation.writers.list()

        You must have ffmpeg or ImageMagick installed in order

    fig : matplotlib Figure, default None
        For greater control over the aesthetics, supply your own figure.

    dpi : int, default 144
        Dots per Inch of the matplotlib figure

    bar_kwargs : dict, default `None` (alpha=.8)
        Other keyword arguments (within a dictionary) forwarded to the 
        matplotlib `barh`/`bar` function. If no value for 'alpha' is given,
        then it is set to .8 by default.
        Some examples:
            `ec` - edgecolor - color of edge of bar. Default is 'white'
            `lw` - width of edge in points. Default is 1.5
            `alpha` - opacity of bars, 0 to 1

    filter_column_colors : bool, default `False`
        When setting n_bars, it's possible that some columns never 
        appear in the animation. Regardless, all columns get assigned
        a color by default. 
        
        For instance, suppose you have 100 columns 
        in your DataFrame, set n_bars to 10, and 15 different columns 
        make at least one appearance in the animation. Even if your 
        colormap has at least 15 colors, it's possible that many 
        bars will be the same color, since each of the 100 columns is
        assigned of the colormaps colors.

        Setting this to `True` will map your colormap to just those 
        columns that make an appearance in the animation, helping
        avoid duplication of colors.

        Setting this to `True` will also have the (possibly unintended)
        consequence of changing the colors of each color every time a 
        new integer for n_bars is used.

        EXPERIMENTAL
        This parameter is experimental and may be changed/removed
        in a later version.


    Returns
    -------
    When `filename` is left as `None`, an HTML5 video is returned as a string.
    Otherwise, a file of the animation is saved and `None` is returned.

    Notes
    -----
    It is possible for some bars to be out of order momentarily during a 
    transition since both height and location change linearly and not 
    directly with respect to their current value. This keeps all the 
    transitions identical.

    Examples
    --------
    Use the `load_data` function to get an example dataset to 
    create an animation.

    df = bcr.load_dataset('covid19')
    bcr.bar_chart_race(
        df=df, 
        filename='covid19_horiz_desc.mp4', 
        orientation='h', 
        sort='desc', 
        n_bars=8, 
        fixed_order=False, 
        fixed_max=True, 
        steps_per_period=10, 
        period_length=500, 
        interpolate_period=False, 
        bar_label_fmt=True, 
        bar_size=.95, 
        period_label={'x': .99, 'y': .8, 'ha': 'right', 'va': 'center'}, 
        period_fmt='%B %d, %Y', 
        period_summary_func=lambda v, r: {'x': .85, 'y': .2, 
                                          's': f'Total deaths: {v.sum()}', 
                                          'ha': 'right', 'size': 11}, 
        perpendicular_bar_func='median', 
        figsize=(5, 3), 
        dpi=144,
        cmap='dark12', 
        title='COVID-19 Deaths by Country', 
        bar_label_size=7, 
        tick_label_size=7, 
        shared_fontdict={'family' : 'Helvetica', 'weight' : 'bold', 'color' : '.1'}, 
        scale='linear', 
        writer=None, 
        fig=None, 
        bar_kwargs={'alpha': .7},
        filter_column_colors=False)        

    Font Help
    ---------
    Font size can also be a string - 'xx-small', 'x-small', 'small',  
        'medium', 'large', 'x-large', 'xx-large', 'smaller', 'larger'
    These sizes are relative to plt.rcParams['font.size'].
    '''
    bcr = _BarChartRace(df, filename, orientation, sort, n_bars, fixed_order, fixed_max,
                        steps_per_period, period_length, interpolate_period, bar_label_position, 
                        bar_label_fmt, bar_size, period_label, period_fmt, period_summary_func, 
                        perpendicular_bar_func, figsize, cmap, title, bar_label_size, 
                        tick_label_size, shared_fontdict, scale, writer, fig, dpi, bar_kwargs, 
                        filter_column_colors)
    return bcr.make_animation()
