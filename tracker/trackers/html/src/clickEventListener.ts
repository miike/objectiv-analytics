import { makeClickEvent, WebTracker } from '@objectiv/tracker-web';
import { findTrackedElementsInDOM } from './findTrackedElementsInDOM';
import { isTrackedElement } from './isTrackedElement';
import { TrackingAttribute } from './TrackingAttributes';

/**
 * Our Click Event listener will traverse the DOM and reconstruct a LocationStack, then use WebTracker to transport it.
 */
export const clickEventListener = (tracker: WebTracker, event: Event, element: HTMLElement) => {
  if (!isTrackedElement(event.target)) {
    return;
  }

  const targetElementId = event.target.getAttribute(TrackingAttribute.objectivElementId);
  const elementId = element.getAttribute(TrackingAttribute.objectivElementId);
  if (targetElementId !== elementId) {
    return;
  }

  const trackedElements = findTrackedElementsInDOM(element).reverse();

  // TODO reconstruct Location Stack from trackedElements
  if (event instanceof PointerEvent) {
    tracker.trackEvent(makeClickEvent({ location_stack: [] }));
  }

  //FocusEvent
  console.log(event);

  console.log(element.dataset, trackedElements);
};
