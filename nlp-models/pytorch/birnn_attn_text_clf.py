import torch
import numpy as np
import math
from sklearn.utils import shuffle


class RNNTextClassifier(torch.nn.Module):
    def __init__(self, vocab_size, n_out=2, embedding_dim=128, cell_size=128, n_layer=1, dropout=0.2):
        super(RNNTextClassifier, self).__init__()
        self.vocab_size = vocab_size
        self.embedding_dim = embedding_dim
        self.cell_size = cell_size
        self.n_layer = n_layer
        self.n_out = n_out
        self.dropout = dropout
        self.build_model()
    # end constructor


    def build_model(self):
        self.encoder = torch.nn.Embedding(self.vocab_size, self.embedding_dim)
        self.fw_lstm = torch.nn.LSTM(input_size=self.embedding_dim,
                                     hidden_size=self.cell_size,
                                     batch_first=True,
                                     dropout=self.dropout)
        self.bw_lstm = torch.nn.LSTM(input_size=self.embedding_dim,
                                     hidden_size=self.cell_size,
                                     batch_first=True,
                                     dropout=self.dropout)
        self.attn_fc = torch.nn.Linear(2*self.cell_size, 1)
        self.fc = torch.nn.Linear(2*self.cell_size, self.n_out)
        self.criterion = torch.nn.CrossEntropyLoss()
        self.optimizer = torch.optim.Adam(self.parameters())
    # end method build_model    


    def bidirectional_rnn(self, X):
        X_reversed = self.reverse(X, 1)
        fw_out, _ = self.fw_lstm(self.encoder(X), None)
        bw_out, _ = self.bw_lstm(self.encoder(X_reversed), None)
        return torch.cat((fw_out, self.reverse(bw_out, 1)), 2) 
    # end method bidirectional_rnn


    def attention(self, X, batch_size):
        reshaped = X.view(-1, 2*self.cell_size)
        reduced = torch.nn.functional.tanh(self.attn_fc(reshaped))
        alphas = torch.nn.functional.softmax(reduced.view(batch_size, -1, 1)) # (batch_size, max_seq_len, 1)
        # (batch, cell_size, seq_len) * (batch, seq_len, 1) -> (batch, cell_size)
        return torch.bmm(torch.transpose(X, 1, 2), alphas).squeeze(2)
    # end method attention


    def forward(self, X, batch_size):
        birnn_out = self.bidirectional_rnn(X)
        attn_out = self.attention(birnn_out, batch_size)
        logits = self.fc(attn_out)
        return logits
    # end method forward


    def fit(self, X, y, n_epoch=10, batch_size=32, en_shuffle=True):
        global_step = 0
        n_batch = int(len(X) / batch_size)
        total_steps = int(n_epoch * n_batch)

        for epoch in range(n_epoch):
            if en_shuffle:
                X, y = shuffle(X, y)
            state = None
            for local_step, (X_batch, y_batch) in enumerate(zip(self.gen_batch(X, batch_size),
                                                                self.gen_batch(y, batch_size))):
                inputs = torch.autograd.Variable(torch.from_numpy(X_batch.astype(np.int64)))
                labels = torch.autograd.Variable(torch.from_numpy(y_batch.astype(np.int64)))
                
                preds = self.forward(inputs, len(X_batch))

                loss = self.criterion(preds, labels)                   # cross entropy loss
                self.optimizer, lr = self.adjust_lr(self.optimizer, global_step, total_steps)
                self.optimizer.zero_grad()                             # clear gradients for this training step
                loss.backward()                                        # backpropagation, compute gradients
                self.optimizer.step()                                  # apply gradients
                global_step += 1

                preds = torch.max(preds,1)[1].data.numpy().squeeze()
                acc = (preds == y_batch).mean()
                if local_step % 100 == 0:
                    print ('Epoch [%d/%d] | Step [%d/%d] | Loss: %.4f | Acc: %.4f | LR: %.4f'
                           %(epoch+1, n_epoch, local_step, n_batch, loss.data[0], acc, lr))
    # end method fit


    def evaluate(self, X_test, y_test, batch_size=32):
        correct = 0
        total = 0
        state = None

        for X_batch, y_batch in zip(self.gen_batch(X_test, batch_size), self.gen_batch(y_test, batch_size)):
            inputs = torch.autograd.Variable(torch.from_numpy(X_batch.astype(np.int64)))
            labels = torch.from_numpy(y_batch.astype(np.int64))

            preds = self.forward(inputs, len(X_batch))

            _, preds = torch.max(preds.data, 1)
            total += labels.size(0)
            correct += (preds == labels).sum()
        print('Test Accuracy of the model: %.4f' % (float(correct) / total)) 
    # end method evaluate


    def gen_batch(self, arr, batch_size):
        for i in range(0, len(arr), batch_size):
            yield arr[i : i + batch_size]
    # end method gen_batch


    def adjust_lr(self, optimizer, current_step, total_steps):
        max_lr = 0.005
        min_lr = 0.001
        decay_rate = math.log(min_lr/max_lr) / (-total_steps)
        lr = max_lr * math.exp(-decay_rate * current_step)
        for param_group in optimizer.param_groups:
            param_group['lr'] = lr
        return optimizer, lr
    # end method adjust_lr


    def reverse(self, X, dim):
        indices = [i for i in range(X.size(dim)-1, -1, -1)]
        indices = torch.autograd.Variable(torch.LongTensor(indices))
        inverted = torch.index_select(X, dim, indices)
        return inverted
    # end method reverse
# end class RNNClassifier