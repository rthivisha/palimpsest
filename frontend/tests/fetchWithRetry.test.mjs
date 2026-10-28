import test from 'node:test';
import assert from 'node:assert';
import { fetchWithInitialRetry } from '../src/utils/fetchWithRetry.ts';

test('fetchWithInitialRetry: succeeds on first attempt without retrying', async () => {
  let callCount = 0;
  const mockFetch = async () => {
    callCount += 1;
    return new Response('ok', { status: 200 });
  };

  const res = await fetchWithInitialRetry('/api/run', {}, 10, mockFetch);
  assert.strictEqual(callCount, 1);
  assert.strictEqual(res.status, 200);
});

test('fetchWithInitialRetry: retries once when initial connection fails before response', async () => {
  let callCount = 0;
  const mockFetch = async () => {
    callCount += 1;
    if (callCount === 1) {
      throw new TypeError('Failed to fetch');
    }
    return new Response('recovered', { status: 200 });
  };

  const res = await fetchWithInitialRetry('/api/run', {}, 10, mockFetch);
  assert.strictEqual(callCount, 2);
  assert.strictEqual(res.status, 200);
});

test('fetchWithInitialRetry: throws after single retry if second attempt also fails', async () => {
  let callCount = 0;
  const mockFetch = async () => {
    callCount += 1;
    throw new TypeError('Failed to fetch');
  };

  await assert.rejects(
    async () => {
      await fetchWithInitialRetry('/api/run', {}, 10, mockFetch);
    },
    {
      name: 'TypeError',
      message: 'Failed to fetch',
    }
  );
  assert.strictEqual(callCount, 2);
});

test('fetchWithInitialRetry: never retries on client AbortError', async () => {
  let callCount = 0;
  const mockFetch = async () => {
    callCount += 1;
    const err = new Error('The operation was aborted');
    err.name = 'AbortError';
    throw err;
  };

  await assert.rejects(
    async () => {
      await fetchWithInitialRetry('/api/run', {}, 10, mockFetch);
    },
    {
      name: 'AbortError',
    }
  );
  assert.strictEqual(callCount, 1);
});

test('stream consumption failure after response is never retried', async () => {
  let fetchCallCount = 0;
  const mockFetch = async () => {
    fetchCallCount += 1;
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode('event: run_started\ndata: {}\n\n'));
      },
      pull(controller) {
        controller.error(new Error('Connection terminated mid-stream'));
      },
    });
    return new Response(stream, { status: 200 });
  };

  const res = await fetchWithInitialRetry('/api/run', {}, 10, mockFetch);
  // Connection was established; response received on 1st call
  assert.strictEqual(fetchCallCount, 1);
  assert.strictEqual(res.status, 200);

  const reader = res.body.getReader();
  const firstChunk = await reader.read();
  assert.strictEqual(firstChunk.done, false);

  // Subsequent stream failure must throw directly to consumer, never re-calling fetch
  await assert.rejects(async () => {
    await reader.read();
  });
  assert.strictEqual(fetchCallCount, 1, 'fetch must NOT be called again once stream has started');
});
