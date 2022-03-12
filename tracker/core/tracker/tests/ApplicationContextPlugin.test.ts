/*
 * Copyright 2021-2022 Objectiv B.V.
 */

import { MockConsoleImplementation } from '@objectiv/testing-tools';
import { ApplicationContextPlugin, ContextsConfig, Tracker, TrackerConfig, TrackerConsole, TrackerEvent } from '../src';

TrackerConsole.setImplementation(MockConsoleImplementation);

const trackerConfig: TrackerConfig = { applicationId: 'app-id' };

describe('ApplicationContextPlugin', () => {
  beforeEach(() => {
    jest.resetAllMocks();
  });

  it('should generate an ApplicationContext when initialized', () => {
    const testApplicationContextPlugin = new ApplicationContextPlugin();
    new Tracker({ ...trackerConfig, plugins: [testApplicationContextPlugin] });
    expect(testApplicationContextPlugin.applicationContext).toEqual({
      __global_context: true,
      _type: 'ApplicationContext',
      id: 'app-id',
    });
  });

  it('should TrackerConsole.error when calling `enrich` before `initialize`', () => {
    const testApplicationContextPlugin = new ApplicationContextPlugin();
    const tracker = new Tracker({ ...trackerConfig });
    testApplicationContextPlugin.enrich(tracker);
    expect(MockConsoleImplementation.error).toHaveBeenCalledWith(
      '｢objectiv:ApplicationContextPlugin｣ Cannot enrich. Make sure to initialize the plugin first.'
    );
  });

  it('should add the ApplicationContext to the Event when `enrich` is executed by the Tracker', async () => {
    const plugins = new ApplicationContextPlugin();
    const testTracker = new Tracker({ ...trackerConfig, plugins: [plugins] });
    const eventContexts: ContextsConfig = {
      global_contexts: [
        { __global_context: true, _type: 'section', id: 'X' },
        { __global_context: true, _type: 'section', id: 'Y' },
      ],
    };
    const testEvent = new TrackerEvent({ _type: 'test-event', ...eventContexts });
    expect(testEvent.global_contexts).toHaveLength(2);
    const trackedEvent = await testTracker.trackEvent(testEvent);
    expect(trackedEvent.global_contexts).toHaveLength(3);
    expect(trackedEvent.global_contexts).toEqual(
      expect.arrayContaining([
        {
          __global_context: true,
          _type: 'ApplicationContext',
          id: 'app-id',
        },
      ])
    );
  });
});
