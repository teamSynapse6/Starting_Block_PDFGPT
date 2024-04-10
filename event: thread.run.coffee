event: thread.run.created
data: { "id": "run_123", "object": "thread.run", "created_at": 1710330640, "assistant_id": "asst_123", "thread_id": "thread_123", "status": "queued", "started_at": null, "expires_at": 1710331240, "cancelled_at": null, "failed_at": null, "completed_at": null, "required_action": null, "last_error": null, "model": "gpt-4-turbo", "instructions": null, "tools": [], "file_ids": [], "metadata": { }, "usage": null }

event: thread.run.queued
data: { "id": "run_123", "object": "thread.run", "created_at": 1710330640, "assistant_id": "asst_123", "thread_id": "thread_123", "status": "queued", "started_at": null, "expires_at": 1710331240, "cancelled_at": null, "failed_at": null, "completed_at": null, "required_action": null, "last_error": null, "model": "gpt-4-turbo", "instructions": null, "tools": [], "file_ids": [], "metadata": { }, "usage": null }

event: thread.run.in_progress
data: { "id": "run_123", "object": "thread.run", "created_at": 1710330640, "assistant_id": "asst_123", "thread_id": "thread_123", "status": "in_progress", "started_at": 1710330641, "expires_at": 1710331240, "cancelled_at": null, "failed_at": null, "completed_at": null, "required_action": null, "last_error": null, "model": "gpt-4-turbo", "instructions": null, "tools": [], "file_ids": [], "metadata": { }, "usage": null }

event: thread.run.step.created
data: { "id": "step_001", "object": "thread.run.step", "created_at": 1710330641, "run_id": "run_123", "assistant_id": "asst_123", "thread_id": "thread_123", "type": "message_creation", "status": "in_progress", "cancelled_at": null, "completed_at": null, "expires_at": 1710331240, "failed_at": null, "last_error": null, "step_details": { "type": "message_creation", "message_creation": { "message_id": "msg_001" } }, "usage": null }

event: thread.run.step.in_progress
data: { "id": "step_001", "object": "thread.run.step", "created_at": 1710330641, "run_id": "run_123", "assistant_id": "asst_123", "thread_id": "thread_123", "type": "message_creation", "status": "in_progress", "cancelled_at": null, "completed_at": null, "expires_at": 1710331240, "failed_at": null, "last_error": null, "step_details": { "type": "message_creation", "message_creation": { "message_id": "msg_001" } }, "usage": null }

event: thread.message.created
data: { "id": "msg_001", "object": "thread.message", "created_at": 1710330641, "assistant_id": "asst_123", "thread_id": "thread_123", "run_id": "run_123", "status": "in_progress", "incomplete_details": null, "incomplete_at": null, "completed_at": null, "role": "assistant", "content": [], "file_ids": [], "metadata": { } }

event: thread.message.in_progress
data: { "id": "msg_001", "object": "thread.message", "created_at": 1710330641, "assistant_id": "asst_123", "thread_id": "thread_123", "run_id": "run_123", "status": "in_progress", "incomplete_details": null, "incomplete_at": null, "completed_at": null, "role": "assistant", "content": [], "file_ids": [], "metadata": { } }

event: thread.message.delta
data: { "id": "msg_001", "object": "thread.message.delta", "delta": { "content": [{ "index": 0, "type": "text", "text": { "value": "Hello", "annotations": [] } }] } }

...

event: thread.message.delta
data: { "id": "msg_001", "object": "thread.message.delta", "delta": { "content": [{ "index": 0, "type": "text", "text": { "value": " today" } }] } }

event: thread.message.delta
data: { "id": "msg_001", "object": "thread.message.delta", "delta": { "content": [{ "index": 0, "type": "text", "text": { "value": "?" } }] } }

event: thread.message.completed
data: { "id": "msg_001", "object": "thread.message", "created_at": 1710330641, "assistant_id": "asst_123", "thread_id": "thread_123", "run_id": "run_123", "status": "completed", "incomplete_details": null, "incomplete_at": null, "completed_at": 1710330642, "role": "assistant", "content": [{ "type": "text", "text": { "value": "Hello! How can I assist you today?", "annotations": [] } }], "file_ids": [], "metadata": { } }

event: thread.run.step.completed
data: { "id": "step_001", "object": "thread.run.step", "created_at": 1710330641, "run_id": "run_123", "assistant_id": "asst_123", "thread_id": "thread_123", "type": "message_creation", "status": "completed", "cancelled_at": null, "completed_at": 1710330642, "expires_at": 1710331240, "failed_at": null, "last_error": null, "step_details": { "type": "message_creation", "message_creation": { "message_id": "msg_001" } }, "usage": { "prompt_tokens": 20, "completion_tokens": 11, "total_tokens": 31 } }

event: thread.run.completed
data: { "id": "run_123", "object": "thread.run", "created_at": 1710330640, "assistant_id": "asst_123", "thread_id": "thread_123", "status": "completed", "started_at": 1710330641, "expires_at": null, "cancelled_at": null, "failed_at": null, "completed_at": 1710330642, "required_action": null, "last_error": null, "model": "gpt-4-turbo", "instructions": null, "tools": [], "file_ids": [], "metadata": { }, "usage": { "prompt_tokens": 20, "completion_tokens": 11, "total_tokens": 31 } }

event: done
data: [DONE]
