import fetchMock from 'jest-fetch-mock';
import {
  ContextsConfig,
  FetchAPITransport,
  QueuedTransport,
  RetryTransport,
  Tracker,
  TrackerEvent,
  TrackerQueue,
  TrackerQueueMemoryStore,
  TransportGroup,
  TransportSwitch,
} from '../src';
import { LogTransport, UnusableTransport } from './mocks';
import { ConfigurableMockTransport } from './mocks/ConfigurableMockTransport';

const testEventName = 'test-event';
const testContexts: ContextsConfig = {
  location_stack: [{ __location_context: true, _context_type: 'section', id: 'test' }],
  global_contexts: [{ __global_context: true, _context_type: 'global', id: 'test' }],
};
const testEvent = new TrackerEvent({ event: testEventName, ...testContexts });

beforeEach(() => {
  jest.useFakeTimers();
});

afterEach(() => {
  jest.useRealTimers();
});

describe('TransportSwitch', () => {
  it('should not pick any TrackerTransport', () => {
    const transport1 = new UnusableTransport();
    const transport2 = new LogTransport();
    transport2.isUsable = () => false;

    expect(transport1.isUsable()).toBe(false);
    expect(transport2.isUsable()).toBe(false);

    spyOn(transport1, 'handle');
    spyOn(transport2, 'handle');

    const transports = new TransportSwitch(transport1, transport2);
    expect(transports.firstUsableTransport).toBe(undefined);
    expect(transports.isUsable()).toBe(false);

    expect(transports.handle(testEvent)).rejects.toEqual(
      'TransportSwitch: no usable Transport found; make sure to verify usability first.'
    );

    expect(transport1.handle).not.toHaveBeenCalled();
    expect(transport2.handle).not.toHaveBeenCalled();
  });

  it('should pick the second TrackerTransport', () => {
    const transport1 = new UnusableTransport();
    const transport2 = new LogTransport();

    expect(transport1.isUsable()).toBe(false);
    expect(transport2.isUsable()).toBe(true);

    spyOn(transport1, 'handle');
    spyOn(transport2, 'handle');

    const transports = new TransportSwitch(transport1, transport2);
    expect(transports.firstUsableTransport).toBe(transport2);
    expect(transports.isUsable()).toBe(true);

    const testTracker = new Tracker({ applicationId: 'app-id', transport: transports });

    testTracker.trackEvent(testEvent);

    expect(transport1.handle).not.toHaveBeenCalled();
    expect(transport2.handle).toHaveBeenCalledWith(expect.objectContaining({ event: testEvent.event }));
  });
});

describe('TransportGroup', () => {
  it('should not handle any TrackerTransport', () => {
    const transport1 = new UnusableTransport();
    const transport2 = new LogTransport();
    transport2.isUsable = () => false;

    expect(transport1.isUsable()).toBe(false);
    expect(transport2.isUsable()).toBe(false);

    spyOn(transport1, 'handle');
    spyOn(transport2, 'handle');

    const transports = new TransportGroup(transport1, transport2);
    expect(transports.usableTransports).toStrictEqual([]);
    expect(transports.isUsable()).toBe(false);

    expect(transports.handle(testEvent)).rejects.toEqual(
      'TransportGroup: no usable Transports found; make sure to verify usability first.'
    );

    expect(transport1.handle).not.toHaveBeenCalled();
    expect(transport2.handle).not.toHaveBeenCalled();
  });

  it('should handle both TrackerTransport', () => {
    const transport1 = new LogTransport();
    const transport2 = new LogTransport();

    expect(transport1.isUsable()).toBe(true);
    expect(transport2.isUsable()).toBe(true);

    spyOn(transport1, 'handle');
    spyOn(transport2, 'handle');

    const transports = new TransportGroup(transport1, transport2);
    expect(transports.usableTransports).toStrictEqual([transport1, transport2]);
    expect(transports.isUsable()).toBe(true);

    const testTracker = new Tracker({ applicationId: 'app-id', transport: transports });

    testTracker.trackEvent(testEvent);

    expect(transport1.handle).toHaveBeenCalled();
    expect(transport2.handle).toHaveBeenCalled();
  });
});

describe('TrackerTransport complex configurations', () => {
  const beacon = new ConfigurableMockTransport({ isUsable: false });
  const fetch = new ConfigurableMockTransport({ isUsable: false });
  const xmlHTTPRequest = new ConfigurableMockTransport({ isUsable: false });
  const pigeon = new ConfigurableMockTransport({ isUsable: false });
  const consoleLog = new ConfigurableMockTransport({ isUsable: false });
  const errorLog = new ConfigurableMockTransport({ isUsable: false });

  beforeEach(() => {
    beacon._isUsable = false;
    fetch._isUsable = false;
    xmlHTTPRequest._isUsable = false;
    pigeon._isUsable = false;
    consoleLog._isUsable = false;
    errorLog._isUsable = false;
    jest.clearAllMocks();
    spyOn(beacon, 'handle');
    spyOn(fetch, 'handle');
    spyOn(xmlHTTPRequest, 'handle');
    spyOn(pigeon, 'handle');
    spyOn(consoleLog, 'handle');
    spyOn(errorLog, 'handle');
  });

  it('should handle to errorLog', () => {
    errorLog._isUsable = true;
    expect(errorLog.isUsable()).toBe(true);

    const sendTransport = new TransportSwitch(beacon, fetch, xmlHTTPRequest, pigeon);
    const sendAndLog = new TransportGroup(sendTransport, consoleLog);
    const transport = new TransportSwitch(sendAndLog, errorLog);

    expect(sendTransport.isUsable()).toBe(false);
    expect(sendAndLog.isUsable()).toBe(false);
    expect(transport.isUsable()).toBe(true);

    const testTracker = new Tracker({ applicationId: 'app-id', transport });

    testTracker.trackEvent(testEvent);

    expect(beacon.handle).not.toHaveBeenCalled();
    expect(fetch.handle).not.toHaveBeenCalled();
    expect(xmlHTTPRequest.handle).not.toHaveBeenCalled();
    expect(pigeon.handle).not.toHaveBeenCalled();
    expect(consoleLog.handle).not.toHaveBeenCalled();
    expect(errorLog.handle).toHaveBeenCalled();
  });

  it('should handle to fetch and consoleLog', () => {
    fetch._isUsable = true;
    expect(fetch.isUsable()).toBe(true);
    consoleLog._isUsable = true;
    expect(consoleLog.isUsable()).toBe(true);

    const sendTransport = new TransportSwitch(beacon, fetch, xmlHTTPRequest, pigeon);
    const sendAndLog = new TransportGroup(sendTransport, consoleLog);
    const transport = new TransportSwitch(sendAndLog, errorLog);

    expect(sendTransport.isUsable()).toBe(true);
    expect(sendAndLog.isUsable()).toBe(true);
    expect(transport.isUsable()).toBe(true);

    const testTracker = new Tracker({ applicationId: 'app-id', transport });

    testTracker.trackEvent(testEvent);

    expect(beacon.handle).not.toHaveBeenCalled();
    expect(fetch.handle).toHaveBeenCalled();
    expect(xmlHTTPRequest.handle).not.toHaveBeenCalled();
    expect(pigeon.handle).not.toHaveBeenCalled();
    expect(consoleLog.handle).toHaveBeenCalled();
    expect(errorLog.handle).not.toHaveBeenCalled();
  });

  it('should handle to consoleLog', () => {
    consoleLog._isUsable = true;
    expect(consoleLog.isUsable()).toBe(true);

    const sendTransport = new TransportSwitch(beacon, fetch, xmlHTTPRequest, pigeon);
    const sendAndLog = new TransportGroup(sendTransport, consoleLog);
    const transport = new TransportSwitch(sendAndLog, errorLog);

    expect(sendTransport.isUsable()).toBe(false);
    expect(sendAndLog.isUsable()).toBe(true);
    expect(transport.isUsable()).toBe(true);

    const testTracker = new Tracker({ applicationId: 'app-id', transport });

    testTracker.trackEvent(testEvent);

    expect(beacon.handle).not.toHaveBeenCalled();
    expect(fetch.handle).not.toHaveBeenCalled();
    expect(xmlHTTPRequest.handle).not.toHaveBeenCalled();
    expect(pigeon.handle).not.toHaveBeenCalled();
    expect(consoleLog.handle).toHaveBeenCalled();
    expect(errorLog.handle).not.toHaveBeenCalled();
  });
});

describe('QueuedTransport', () => {
  it('should do nothing if the given transport is not usable', () => {
    const logTransport = new UnusableTransport();
    spyOn(logTransport, 'handle').and.callThrough();
    const trackerQueue = new TrackerQueue();

    const testQueuedTransport = new QueuedTransport({
      queue: trackerQueue,
      transport: logTransport,
    });

    expect(testQueuedTransport.isUsable()).toBe(false);
    expect(trackerQueue.store.length).toBe(0);
    expect(logTransport.handle).not.toHaveBeenCalled();
    expect(setInterval).not.toHaveBeenCalled();
  });

  it('should queue events in the TrackerQueue and send them in batches via the LogTransport', async () => {
    const queueStore = new TrackerQueueMemoryStore();
    const logTransport = new LogTransport();
    const trackerQueue = new TrackerQueue({ store: queueStore });

    const testQueuedTransport = new QueuedTransport({
      queue: trackerQueue,
      transport: logTransport,
    });

    spyOn(trackerQueue, 'processFunction').and.callThrough();

    expect(testQueuedTransport.isUsable()).toBe(true);

    expect(trackerQueue.processFunction).not.toBeUndefined();
    expect(trackerQueue.processFunction).not.toHaveBeenCalled();
    expect(setInterval).toHaveBeenCalledTimes(1);

    await testQueuedTransport.handle(testEvent);

    expect(queueStore.length).toBe(1);
    expect(trackerQueue.processFunction).not.toHaveBeenCalled();

    await trackerQueue.run();

    expect(trackerQueue.processingEventIds).toHaveLength(0);
    expect(trackerQueue.processFunction).toHaveBeenCalledTimes(1);
    expect(trackerQueue.processFunction).toHaveBeenNthCalledWith(1, testEvent);
  });
});

describe('RetryTransport', () => {
  beforeEach(() => {
    fetchMock.enableMocks();
  });

  afterEach(() => {
    fetchMock.resetMocks();
  });

  it('should not accept 0 or negative minTimeoutMs', () => {
    expect(() => new RetryTransport({ transport: new UnusableTransport(), minTimeoutMs: 0 })).toThrow(
      'minTimeoutMs must be at least 1'
    );
    expect(() => new RetryTransport({ transport: new UnusableTransport(), minTimeoutMs: -10 })).toThrow(
      'minTimeoutMs must be at least 1'
    );
  });

  it('should not accept minTimeoutMs bigger than maxTimeoutMs', () => {
    expect(() => new RetryTransport({ transport: new UnusableTransport(), minTimeoutMs: 10, maxTimeoutMs: 5 })).toThrow(
      'minTimeoutMs cannot be bigger than maxTimeoutMs'
    );
  });

  it('should do nothing if the given transport is not usable', () => {
    const unusableTransport = new UnusableTransport();
    spyOn(unusableTransport, 'handle').and.callThrough();

    const retryTransport = new RetryTransport({ transport: unusableTransport });

    expect(unusableTransport.isUsable()).toBe(false);
    expect(retryTransport.isUsable()).toBe(false);
    expect(unusableTransport.handle).not.toHaveBeenCalled();
  });

  it('should not retry', async () => {
    const retryTransport = new RetryTransport({ transport: new FetchAPITransport({ endpoint: 'http://localhost' }) });
    spyOn(retryTransport, 'retry').and.callThrough();

    await retryTransport.handle(testEvent);

    expect(retryTransport.retry).not.toHaveBeenCalled();
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('should retry once', async () => {
    jest.useRealTimers();
    const mockedError = new Error('You shall not pass!');
    fetchMock.mockRejectOnce(mockedError);
    const retryTransport = new RetryTransport({
      transport: new FetchAPITransport({ endpoint: 'http://localhost' }),
      minTimeoutMs: 1,
      maxTimeoutMs: 1,
      retryFactor: 1,
    });
    spyOn(retryTransport, 'retry').and.callThrough();

    await retryTransport.handle(testEvent);

    expect(retryTransport.attemptCount).toBe(2);
    expect(retryTransport.retry).toHaveBeenCalledTimes(1);
    expect(retryTransport.retry).toHaveBeenNthCalledWith(1, mockedError, [testEvent]);
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it('should retry three times', async () => {
    jest.useRealTimers();
    const mockedError = new Error('You shall not pass!');
    fetchMock.mockReject(mockedError);
    const retryTransport = new RetryTransport({
      transport: new FetchAPITransport({ endpoint: 'http://localhost' }),
      maxAttempts: 3,
      minTimeoutMs: 1,
      maxTimeoutMs: 1,
      retryFactor: 1,
    });

    spyOn(retryTransport, 'retry').and.callThrough();
    spyOn(retryTransport, 'handle').and.callThrough();

    await retryTransport.handle(testEvent);

    expect(retryTransport.attemptCount).toBe(4);
    expect(retryTransport.retry).toHaveBeenCalledTimes(4);
    expect(retryTransport.retry).toHaveBeenNthCalledWith(1, mockedError, [testEvent]);
    expect(retryTransport.retry).toHaveBeenNthCalledWith(2, mockedError, [testEvent]);
    expect(retryTransport.retry).toHaveBeenNthCalledWith(3, mockedError, [testEvent]);
    expect(retryTransport.retry).toHaveBeenNthCalledWith(4, mockedError, [testEvent]);
    expect(retryTransport.handle).toHaveBeenCalledTimes(4);
    expect(fetch).toHaveBeenCalledTimes(4);
  });

  it('should stop retrying if we reached maxRetryMs', async () => {
    jest.useRealTimers();
    fetchMock.mockResponse(() => new Promise((resolve) => setTimeout(resolve, 100)));
    const retryTransport = new RetryTransport({
      transport: new FetchAPITransport({ endpoint: 'http://localhost' }),
      minTimeoutMs: 1,
      maxTimeoutMs: 1,
      retryFactor: 1,
      maxRetryMs: 1,
    });
    spyOn(retryTransport, 'retry').and.callThrough();

    await retryTransport.handle(testEvent);

    expect(retryTransport.retry).toHaveBeenCalledTimes(1);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(retryTransport.errors[0]).toStrictEqual(new Error('maxRetryMs reached'));
  });
});
