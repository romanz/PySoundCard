from cffi import FFI
import atexit
import numpy as np
import warnings

"""PySoundCard is an audio library based on PortAudio, CFFI and NumPy

PySoundCard can play and record audio data. Audio devices are supported
through PortAudio[1], which is a free, cross-platform, open-source
audio I/O library that runs on may platforms including Windows, OS X,
and Unix (OSS/ALSA). It is accessed through CFFI[2], which is a
foreign function interface for Python calling C code. CFFI is
supported for CPython 2.6+, 3.x and PyPy 2.0+. PySoundCard represents
audio data as NumPy arrays.

PySoundCard is inspired by PyAudio[3]. Its main difference is that it
uses CFFI instead of a CPython extension and tries to implement a more
pythonic interface. Its performance characteristics are very similar.

[1]: http://www.portaudio.com/
[2]: http://cffi.readthedocs.org/
[3]: http://people.csail.mit.edu/hubert/pyaudio/

The basic building block of audio input/output in PySoundCard are
streams. Streams represent sound cards, both for audio playback and
recording. Every stream has a sample rate, a block size, an input
device and/or an output device.

There are two modes of operation for streams: read/write and callback
mode.

In read/write mode, two methods are used to play/record audio: For
playback, you write to a stream. For recording, you read from a
stream. You can read/write up to one block of audio data to a stream
without having to wait for it to play.

In callback mode, a callback function is defined, which will be called
asynchronously whenever there is a new block of audio data available
to read or write. The callback function must then provide/consume one
block of audio data.

A stream can be either full duplex (both input and output) or half
duplex (either input or output). This is determined by specifying one
or two devices for the stream. Both devices must be part of the same
audio API.

Use the function apis() to get a list of all available apis. Use the
function devices() to get a list of all available devices. There are
additional functions to get the default devices and api. If a stream
is created without specifying a device, the default devices are used.

Both devices and apis are simple dictionaries that contain information
and configuration options. Many device options can be changed simply
by modifying the dictionary before passing it to the stream
constructor. This includes the number of channels, the desired
latency, and the audio data format.

PySoundCard is BSD licensed.
(c) 2013, Bastian Bechtold

"""

ffi = FFI()
ffi.cdef("""
typedef int PaError;
typedef enum PaErrorCode
{
    paNoError = 0,

    paNotInitialized = -10000,
    paUnanticipatedHostError,
    paInvalidChannelCount,
    paInvalidSampleRate,
    paInvalidDevice,
    paInvalidFlag,
    paSampleFormatNotSupported,
    paBadIODeviceCombination,
    paInsufficientMemory,
    paBufferTooBig,
    paBufferTooSmall,
    paNullCallback,
    paBadStreamPtr,
    paTimedOut,
    paInternalError,
    paDeviceUnavailable,
    paIncompatibleHostApiSpecificStreamInfo,
    paStreamIsStopped,
    paStreamIsNotStopped,
    paInputOverflowed,
    paOutputUnderflowed,
    paHostApiNotFound,
    paInvalidHostApi,
    paCanNotReadFromACallbackStream,
    paCanNotWriteToACallbackStream,
    paCanNotReadFromAnOutputOnlyStream,
    paCanNotWriteToAnInputOnlyStream,
    paIncompatibleStreamHostApi,
    paBadBufferPtr
} PaErrorCode;

PaError Pa_Initialize(void);
PaError Pa_Terminate(void);
int Pa_GetVersion(void);
const char *Pa_GetVersionText(void);

typedef int PaDeviceIndex;

typedef struct PaHostApiInfo {
    int structVersion;
    enum PaHostApiTypeId type;
    const char *name;
    int deviceCount;
    PaDeviceIndex defaultInputDevice;
    PaDeviceIndex defaultOutputDevice;
} PaHostApiInfo;

typedef int PaHostApiIndex;

PaHostApiIndex Pa_GetHostApiCount();
const PaHostApiInfo *Pa_GetHostApiInfo(PaHostApiIndex);

typedef double PaTime;

typedef struct PaDeviceInfo {
    int structVersion;
    const char *name;
    PaHostApiIndex hostApi;
    int maxInputChannels;
    int maxOutputChannels;
    PaTime defaultLowInputLatency;
    PaTime defaultLowOutputLatency;
    PaTime defaultHighInputLatency;
    PaTime defaultHighOutputLatency;
    double defaultSampleRate;
} PaDeviceInfo;

PaDeviceIndex Pa_GetDeviceCount(void);
const PaDeviceInfo *Pa_GetDeviceInfo(PaDeviceIndex);

PaHostApiIndex Pa_GetDefaultHostApi(void);
PaDeviceIndex Pa_GetDefaultInputDevice(void);
PaDeviceIndex Pa_GetDefaultOutputDevice(void);

const char *Pa_GetErrorText(PaError);

typedef void PaStream;
typedef unsigned long PaSampleFormat;

typedef struct PaStreamParameters {
    PaDeviceIndex device;
    int channelCount;
    PaSampleFormat sampleFormat;
    PaTime suggestedLatency;
    void *hostApiSpecificStreamInfo;
} PaStreamParameters;

typedef unsigned long PaStreamFlags;

typedef struct PaStreamCallbackTimeInfo{
    PaTime inputBufferAdcTime;
    PaTime currentTime;
    PaTime outputBufferDacTime;
} PaStreamCallbackTimeInfo;

typedef unsigned long PaStreamCallbackFlags;

typedef int PaStreamCallback(const void*, void*, unsigned long,
                             const PaStreamCallbackTimeInfo*,
                             PaStreamCallbackFlags, void*);
typedef void PaStreamFinishedCallback(void*);

typedef struct PaStreamInfo {
    int structVersion;
    PaTime inputLatency;
    PaTime outputLatency;
    double sampleRate;
} PaStreamInfo;

PaError Pa_OpenStream(PaStream**, const PaStreamParameters*,
		      const PaStreamParameters*, double,
                      unsigned long, PaStreamFlags,
		      PaStreamCallback*, void*);
PaError Pa_CloseStream (PaStream*);
PaError Pa_SetStreamFinishedCallback(PaStream*, PaStreamFinishedCallback*);
PaError Pa_StartStream (PaStream*);
PaError Pa_StopStream (PaStream*);
PaError Pa_AbortStream (PaStream*);
PaError Pa_IsStreamStopped (PaStream*);
PaError Pa_IsStreamActive (PaStream*);
const PaStreamInfo *Pa_GetStreamInfo (PaStream*);
PaTime Pa_GetStreamTime (PaStream*);
double Pa_GetStreamCpuLoad (PaStream*);
PaError Pa_ReadStream (PaStream*, void*, unsigned long);
PaError Pa_WriteStream (PaStream*, const void*, unsigned long);
signed long Pa_GetStreamReadAvailable (PaStream*);
signed long Pa_GetStreamWriteAvailable (PaStream*);
PaError Pa_GetSampleSize (PaSampleFormat);
void Pa_Sleep (long);
""")


continue_flag = 0
complete_flag = 1
abort_flag = 2

_np2pa = {
    np.dtype('float32'): 0x01,
    np.dtype('int32'):   0x02,
    np.dtype('int16'):   0x08,
    np.dtype('int8'):    0x10,
    np.dtype('uint8'):   0x20
}

_pa = ffi.dlopen('portaudio')
_pa.Pa_Initialize()
atexit.register(_pa.Pa_Terminate)


def hostapi_info(index=None):
    """Return a generator with information about each host API.

    If index is given, only one struct for the given host API is
    returned."""
    if index is None:
        return (hostapi_info(i) for i in range(_pa.Pa_GetHostApiCount()))
    else:
        info = _pa.Pa_GetHostApiInfo(index)
        if info == ffi.NULL:
            raise RuntimeError("Invalid host API")
        assert info.structVersion == 1
        return {'name': ffi.string(info.name).decode(errors='ignore'),
                'default_input_device': info.defaultInputDevice,
                'default_output_device': info.defaultOutputDevice}


def device_info(index=None):
    """Return a generator with information about each device.

    If index is given, only one struct for the given device is
    returned."""
    if index is None:
        return (device_info(i) for i in range(_pa.Pa_GetDeviceCount()))
    else:
        info = _pa.Pa_GetDeviceInfo(index)
        if info == ffi.NULL:
            raise RuntimeError("Invalid device")
        assert info.structVersion == 2

        if 'DirectSound' in hostapi_info(info.hostApi)['name']:
            enc = 'mbcs'
        else:
            enc = 'utf-8'

        return {'name': ffi.string(info.name).decode(encoding=enc,
                                                     errors='ignore'),
                'hostapi': info.hostApi,
                'max_input_channels': info.maxInputChannels,
                'max_output_channels': info.maxOutputChannels,
                'default_low_input_latency': info.defaultLowInputLatency,
                'default_low_output_latency': info.defaultLowOutputLatency,
                'default_high_input_latency': info.defaultHighInputLatency,
                'default_high_output_latency': info.defaultHighOutputLatency,
                'default_samplerate': info.defaultSampleRate}


def default_hostapi():
    """Return default host API index."""
    return _pa.Pa_GetDefaultHostApi()


def default_input_device():
    """Return default input device index."""
    idx = _pa.Pa_GetDefaultInputDevice()
    if idx < 0:
        raise RuntimeError("No default input device available")
    return idx


def default_output_device():
    """Return default output device index."""
    idx = _pa.Pa_GetDefaultOutputDevice()
    if idx < 0:
        raise RuntimeError("No default output device available")
    return idx


def pa_version():
    """Returns the version information about the portaudio library."""
    return (_pa.Pa_GetVersion(), ffi.string(_pa.Pa_GetVersionText()).decode())


class _StreamBase(object):

    """Base class for Stream, InputStream and OutputStream."""

    def __init__(self, stream_parameters_in, stream_parameters_out,
                 samplerate, blocksize, finished_callback,
                 clip_off=False, dither_off=False,
                 never_drop_input=False,
                 prime_output_buffers_using_stream_callback=False):
        if blocksize is None:
            blocksize = init.blocksize

        stream_flags = 0x0
        if clip_off:
            stream_flags |= 0x00000001
        if dither_off:
            stream_flags |= 0x00000002
        if never_drop_input:
            stream_flags |= 0x00000004
        if prime_output_buffers_using_stream_callback:
            stream_flags |= 0x00000008

        self._stream = ffi.new("PaStream**")
        err = _pa.Pa_OpenStream(self._stream, stream_parameters_in,
                                stream_parameters_out, samplerate, blocksize,
                                stream_flags, self._callback, ffi.NULL)
        self._handle_error(err)

        # dereference PaStream** --> PaStream*
        self._stream = self._stream[0]

        # set some stream information
        info = _pa.Pa_GetStreamInfo(self._stream)
        if info == ffi.NULL:
            raise RuntimeError("Could not obtain stream info!")
        self._input_latency = info.inputLatency
        self._output_latency = info.outputLatency
        self.samplerate = info.sampleRate
        self.blocksize = blocksize

        if finished_callback:
            @ffi.callback("PaStreamFinishedCallback")
            def finished_callback_stub(userData):
                finished_callback()
            self._finished_callback = finished_callback_stub
            err = _pa.Pa_SetStreamFinishedCallback(self._stream,
                                                   self._finished_callback)
            self._handle_error(err)

    # Avoid confusion if something goes wrong before assigning self._stream:
    _stream = ffi.NULL

    # To be overwritten in derived classes if callback is requested:
    _callback = ffi.NULL

    def _handle_error(self, err):
        # all error codes are negative:
        if err >= 0:
            return err
        errstr = ffi.string(_pa.Pa_GetErrorText(err)).decode()
        if err == -9981 or err == -9980:
            # InputOverflowed and OuputUnderflowed are non-fatal:
            warnings.warn("%.4f: %s" % (self.time(), errstr),
                          RuntimeWarning, stacklevel=2)
            return err
        else:
            raise RuntimeError("%.4f: %s" % (self.time(), errstr))

    def __del__(self):
        # Close stream at garbage collection
        self.close()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, type, value, tb):
        self.stop()
        self.close()

    def start(self):
        """Commence audio processing.

        If successful, the stream is considered active.

        """
        err = _pa.Pa_StartStream(self._stream)
        if err == _pa.paStreamIsNotStopped:
            return
        self._handle_error(err)

    def stop(self):
        """Terminate audio processing.

        This waits until all pending audio buffers have been played
        before it returns. If successful, the stream is considered
        inactive.

        """
        err = _pa.Pa_StopStream(self._stream)
        if err == _pa.paStreamIsStopped:
            return
        self._handle_error(err)

    def abort(self):
        """Terminate audio processing immediately.

        This does not wait for pending audio buffers. If successful,
        the stream is considered inactive.

        """
        err = _pa.Pa_AbortStream(self._stream)
        if err == _pa.paStreamIsStopped:
            return
        self._handle_error(err)

    def close(self):
        """Close the stream.

        Can be called multiple times.
        If the audio stream is active any pending buffers are discarded
        as if abort() had been called.

        """
        _pa.Pa_CloseStream(self._stream)
        # There might be errors if _pa.Pa_Terminate() has been called
        # already or if the stream has been closed before.
        # Those errors are ignored here, it's too late anyway ...

    def is_active(self):
        """Determine whether the stream is active.

        A stream is active after a successful call to start(). It
        becomes inactive as a result to stop() or abort() or a return
        value other than continue from the stream callback.

        """
        return self._handle_error(_pa.Pa_IsStreamActive(self._stream)) == 1

    def is_stopped(self):
        """Determine whether a stream is stopped.

        A stream is stopped before the first call to start() and after
        a successful call to stop() or abort(). If the stream callback
        returns a value other than continue, the stream is NOT
        considered stopped.

        """
        return self._handle_error(_pa.Pa_IsStreamStopped(self._stream)) == 1

    def time(self):
        """Returns the current stream time in seconds.

        This is the same time that is given to the stream callback. It
        is monotonically increasing and is not affected by starting or
        stopping the stream. This time may be used for synchronizing
        other events to the audio stream.

        """
        return _pa.Pa_GetStreamTime(self._stream)

    def cpu_load(self):
        """Retrieve CPU usage information for the specified stream.

        A floating point number between 0.0 and 1.0 that is a fraction
        of the total CPU time consumed by the stream callback audio
        processing within portaudio. This excludes time spent in the
        cffi and Python. This function does not work with blocking
        read/write streams.

        """
        return _pa.Pa_GetStreamCpuLoad(self._stream)


class _Reader(object):

    _input_channels = None
    _input_dtype = None

    def read_length(self):
        """The number of frames that can be written without waiting."""
        return _pa.Pa_GetStreamReadAvailable(self._stream)

    def read(self, frames, raw=False):
        """Read samples from an input stream.

        The function does not return until the required number of
        frames has been read. This may involve waiting for the
        operating system to supply the data.

        If raw data is requested, the raw cffi data buffer is
        returned. Otherwise, a numpy array of the appropriate dtype
        with one column per channel is returned.

        """
        num_bytes = (self._input_channels *
                     self._input_dtype.itemsize * frames)
        data = ffi.new("signed char[]", num_bytes)
        self._handle_error(_pa.Pa_ReadStream(self._stream, data, frames))
        if not raw:
            data = np.frombuffer(ffi.buffer(data), dtype=self._input_dtype)
            data.shape = frames, self._input_channels
        return data


class _Writer(object):

    _output_channels = None
    _output_dtype = None

    def write_length(self):
        """The number of frames that can be read without waiting."""
        return _pa.Pa_GetStreamWriteAvailable(self._stream)

    def write(self, data):
        """Write samples to an output stream.

        As much as one blocksize of audio data will be played
        without blocking. If more than one blocksize was provided,
        the function will only return when all but one blocksize
        has been played.

        Data will be converted to a numpy matrix. Multichannel data
        should be provided as a (frames, channels) matrix. If the
        data is provided as a 1-dim array, it will be treated as mono
        data and will be played on all channels simultaneously. If the
        data is provided as a 2-dim matrix and fewer tracks are
        provided than channels, silence will be played on the missing
        channels. Similarly, if more tracks are provided than there
        are channels, the extraneous channels will not be played.

        """
        frames = len(data)
        channels = self._output_channels

        if (not isinstance(data, np.ndarray) or
                data.dtype != self._output_dtype):
            data = np.array(data, dtype=self._output_dtype)
        if len(data.shape) == 1:
            # broadcast 1D arrays to (n,1) matrices
            data = np.asmatrix(data).T
        elif len(data.shape) == 2 and data.shape[1] == 1:
            # play mono signals on all channels
            data = np.tile(data, (1, channels))
        if data.shape[1] > channels:
            data = data[:, :channels]
        if data.shape < (frames, channels):
            # if less data is available than requested, pad with zeros.
            tmp = data
            data = np.zeros((frames, channels), dtype=self._output_dtype)
            data[:tmp.shape[0], :tmp.shape[1]] = tmp

        data = data.ravel().tostring()
        err = _pa.Pa_WriteStream(self._stream, data, frames)
        self._handle_error(err)


def _setup_stream_parameters(kind, device, channels, dtype, latency,
                             samplerate):
    """Generate PaStreamParameters struct."""
    assert kind in ('input', 'output')

    if device is None:
        device = globals()['default_' + kind + '_device']()
    info = device_info(device)
    if channels is None:
        channels = info['max_' + kind + '_channels']
    if latency in (None, 'low'):
        latency = info['default_low_' + kind + '_latency']
    elif latency == 'high':
        latency = info['default_high_' + kind + '_latency']
    dtype = np.dtype(dtype)
    try:
        sample_format = _np2pa[dtype]
    except KeyError:
        raise ValueError("Invalid " + kind + " sample format")
    if samplerate is None:
        samplerate = info['default_samplerate']
    stream_parameters = ffi.new(
        "PaStreamParameters*",
        (device, channels, sample_format, latency, ffi.NULL))
    return stream_parameters, channels, dtype, samplerate


def _get_buffer(ptr, frames, channels, dtype):
    """Create NumPy array from a pointer to some memory."""
    framesize = channels * dtype.itemsize
    data = np.frombuffer(ffi.buffer(ptr, frames * framesize), dtype=dtype)
    data.shape = -1, channels
    return data


def _time_dict(time):
    """Convert PaStreamCallbackTimeInfo struct to dict."""
    return {'input_adc_time':  time.inputBufferAdcTime,
            'current_time':    time.currentTime,
            'output_dac_time': time.outputBufferDacTime}


class Stream(_StreamBase, _Reader, _Writer):

    """Streams handle audio input and output to your application.

    Each stream operates at a specific sample rate with specific
    sample formats and buffer sizes. Each stream can either be half
    duplex (input only or output only) or full duplex (both input and
    output). For full duplex operation, the input and output device
    must use the same audio api.

    Once a stream has been created, audio processing can be started
    and stopped multiple times using start(), stop() and abort(). The
    functions is_active() and is_stopped() can be used to check this.

    The functions info(), time() and cpu_load() can be used to get
    additional information about the stream.

    Data can be read and written to the stream using read() and
    write(). Use read_length() and write_length() to see how many
    frames can be read or written at the current time.

    Alternatively, a callback can be specified which is called
    whenever there is data available to read or write.

    """

    def __init__(self, samplerate=None, blocksize=0,
                 input_device=None, input_channels=None,
                 input_dtype='float32', input_latency=None,
                 output_device=None, output_channels=None,
                 output_dtype='float32', output_latency=None,
                 callback=None, finished_callback=None,
                 **flags):
        """Open a new stream.

        If no input or output device is specified, the
        default input/output device is taken.

        If a callback is given, it will be called whenever the stream
        is active and data is available to read or write. If a
        finished_callback is given, it will be called whenever the
        stream is stopped or aborted. If a callback is given, read()
        and write() should not be used.

        The callback should have a signature like this:

        callback(input, output, time, status) -> flag

        where input is the recorded data as a NumPy array, output is
        another NumPy array (with uninitialized content), where the data
        for playback has to be written to (using indexing).
        time is a dictionary with some timing information, and
        status indicates whether input or output buffers have
        been inserted or dropped to overcome underflow or overflow
        conditions.

        The function must return one of continue_flag, complete_flag or
        abort_flag.  complete_flag and abort_flag act as if stop() or
        abort() had been called, respectively.  continue_flag resumes
        normal audio processing.

        The finished_callback should be a function with no arguments
        and no return values.

        """
        stream_parameters_in, self._input_channels, self._input_dtype, \
            input_samplerate = _setup_stream_parameters(
                'input', input_device, input_channels, input_dtype,
                input_latency, samplerate)

        stream_parameters_out, self._output_channels, self._output_dtype, \
            output_samplerate = _setup_stream_parameters(
                'output', output_device, output_channels, output_dtype,
                output_latency, samplerate)

        if input_samplerate != output_samplerate:
            raise RuntimeError(
                "Input and output device must have the same samplerate")

        if callback:

            @ffi.callback("PaStreamCallback")
            def callback_stub(input_ptr, output_ptr, frames, time, status, _):
                input = _get_buffer(input_ptr, frames, self._input_channels,
                                    self._input_dtype)
                output = _get_buffer(output_ptr, frames, self._output_channels,
                                     self._output_dtype)
                return callback(input, output, _time_dict(time), status)

            self._callback = callback_stub

        super(Stream, self).__init__(stream_parameters_in,
                                     stream_parameters_out, input_samplerate,
                                     blocksize, finished_callback, **flags)

        self.input_device = stream_parameters_in.device
        self.output_device = stream_parameters_out.device
        self.input_channels = self._input_channels
        self.output_channels = self._output_channels
        self.input_dtype = self._input_dtype.name
        self.output_dtype = self._output_dtype.name
        self.input_latency = self._input_latency
        self.output_latency = self._output_latency


class InputStream(_StreamBase, _Reader):
    def __init__(self, samplerate=None, blocksize=0, device=None,
                 channels=None, dtype='float32', latency=None,
                 callback=None, finished_callback=None, **flags):
        stream_parameters, self._input_channels, self._input_dtype, \
            samplerate = _setup_stream_parameters(
                'input', device, channels, dtype, latency, samplerate)

        if callback:

            @ffi.callback("PaStreamCallback")
            def callback_stub(input_ptr, output_ptr, frames, time, status, _):
                data = _get_buffer(input_ptr, frames, self._input_channels,
                                   self._input_dtype)
                return callback(data, _time_dict(time), status)

            self._callback = callback_stub

        super(InputStream, self).__init__(
            stream_parameters, ffi.NULL,
            samplerate, blocksize, finished_callback, **flags)

        self.device = stream_parameters.device
        self.channels = self._input_channels
        self.dtype = self._input_dtype.name
        self.latency = self._input_latency


class OutputStream(_StreamBase, _Writer):
    def __init__(self, samplerate=None, blocksize=0, device=None,
                 channels=None, dtype='float32', latency=None,
                 callback=None, finished_callback=None, **flags):
        stream_parameters, self._output_channels, self._output_dtype, \
            samplerate = _setup_stream_parameters(
                'output', device, channels, dtype, latency, samplerate)

        if callback:

            @ffi.callback("PaStreamCallback")
            def callback_stub(input_ptr, output_ptr, frames, time, status, _):
                data = _get_buffer(output_ptr, frames, self._output_channels,
                                   self._output_dtype)
                return callback(data, _time_dict(time), status)

            self._callback = callback_stub

        super(OutputStream, self).__init__(
            ffi.NULL, stream_parameters,
            samplerate, blocksize, finished_callback, **flags)

        self.device = stream_parameters.device
        self.channels = self._output_channels
        self.dtype = self._output_dtype.name
        self.latency = self._output_latency
