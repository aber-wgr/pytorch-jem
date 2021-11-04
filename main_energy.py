import torch
import torch.nn as nn
import torch.nn.functional as F
import net
from torch.nn.parameter import Parameter
import utils
import numpy as np

eta = 20
alpha = 1.0
sigma = 0.01
buffer_size = 10000
#buffer_size = 1000
rou = 0.05

B = utils.ReplayBuffer(buffer_size)
m_uniform = torch.distributions.uniform.Uniform(torch.tensor([-1.0]), torch.tensor([1.0]))
B.add(m_uniform.sample((100, 784)).squeeze())

def LogSumExp(x):
    x = torch.logsumexp(x, 1)
    x = x.view(len(x), 1)
    return x

def Sample(f, batch_size, dim, device):
    m_uniform = torch.distributions.uniform.Uniform(torch.tensor([-1.0]), torch.tensor([1.0]))
    m_normal = torch.distributions.normal.Normal(torch.tensor([0.0]), torch.tensor([1.0]))

    batch_size1 = int(batch_size*(1-rou))
    batch_size2 = batch_size - batch_size1
    x1 = torch.stack(B.get_batch(batch_size1))
    x2 = m_uniform.sample((batch_size2, dim)).squeeze()
    x = torch.cat([x1,x2],dim=0)
    x = x.to(device)
    x.requires_grad_(True)
    for i in range(eta):
        jac = net.jacobian(f,x)
        if torch.isnan(jac).any():
            print("jac nan")
            exit(1)
        x = x + alpha * jac + sigma * m_normal.sample(x.shape).squeeze().to(device)
    x = x.detach()
    B.add(x.cpu())
    return x

def train_vanilla(loader_train, model_obj, optimizer, loss_fn, device, total_epoch, epoch):
    
    model_obj.train() # モデルを学習モードに変更
 
    # ミニバッチごとに学習
    running_loss = 0
    for data, targets in loader_train:
 
        data = data.to(device) # GPUを使用するため，to()で明示的に指定
        targets = targets.to(device) # 同上
 
        optimizer.zero_grad() # 勾配を初期化
        outputs = model_obj(data) # 順伝播の計算
        loss = loss_fn(outputs, targets) # 誤差を計算
        running_loss += loss.item()
 
        loss.backward() # 誤差を逆伝播させる
        optimizer.step() # 重みを更新する
    
    train_loss = running_loss / len(loader_train)

    print ('Train Loss: %.4f' % (train_loss))
 
 
# テスト用関数
def test_vanilla(loader_test, trained_model, loss_fn, device):
 
    trained_model.eval() # モデルを推論モードに変更
    correct = 0 # 正解率計算用の変数を宣言
    running_loss = 0 
    # ミニバッチごとに推論
    with torch.no_grad(): # 推論時には勾配は不要
        for data, targets in loader_test:
 
            data = data.to(device) #  GPUを使用するため，to()で明示的に指定
            targets = targets.to(device) # 同上
 
            outputs = trained_model(data) # 順伝播の計算
 
            # 推論結果の取得と正誤判定
            _, predicted = torch.max(outputs.data, 1) # 確率が最大のラベルを取得
            correct += predicted.eq(targets.data.view_as(predicted)).sum() # 正解ならば正解数をカウントアップ

            loss = loss_fn(outputs, targets)
            running_loss += loss.item()
    
    # 正解率を計算
    data_num = len(loader_test.dataset) # テストデータの総数
    val_loss = running_loss / len(loader_test)
    print('\nTest Accuracy: {}/{} ({:.1f}%) loss: {:.4f}\n'.format(correct, data_num, 100. * correct / data_num, val_loss))


# 学習用関数
def train_energy(loader_train, model_obj, optimizer, loss_fn, device, total_epoch, epoch):
    
    model_obj.train() # モデルを学習モードに変更

    # ミニバッチごとに学習
    running_loss = 0
    running_elf_loss = 0
    running_gen_loss = 0
    step = 0
    for data, targets in loader_train:
        if step % 100 == 0:
            print("step={}".format(step))
        step += 1
        LogSumExpf = lambda x: LogSumExp(model_obj(x))
        # GPUを使用するため，to()で明示的に指定
        data = data.to(device)
        targets = targets.to(device) # 同上

        optimizer.zero_grad() # 勾配を初期化
        outputs = model_obj(data) # 順伝播の計算
        loss_elf = loss_fn(outputs, targets) # 誤差を計算
        data_sample = Sample(LogSumExpf, data.shape[0], data.shape[1], device)
        loss_gen =-(LogSumExpf(data) - LogSumExpf(data_sample)).mean()
        loss = loss_elf + loss_gen

        if torch.isnan(loss_elf):
            print("loss_elf nan")
            exit(1)
        if torch.isnan(loss_gen):
            print("loss_gen nan")
            exit(1)
            
        running_loss += loss.item()
        running_elf_loss += loss_elf
        running_gen_loss += loss_gen
        with torch.autograd.detect_anomaly(): 
            loss.backward()
        optimizer.step() # 重みを更新する

    train_loss = running_loss / len(loader_train)
    train_gen_loss = running_gen_loss / len(loader_train)
    train_elf_loss = running_elf_loss / len(loader_train)
    print ('Train ELF loss %.4f, GEN loss %.4f, Total Loss: %.4f' % (train_elf_loss, train_gen_loss, train_loss))
 
 
# テスト用関数
def test_energy(loader_test, trained_model, loss_fn, device):
 
    trained_model.eval() # モデルを推論モードに変更
    correct = 0 # 正解率計算用の変数を宣言
    running_loss = 0 
    # ミニバッチごとに推論
    with torch.no_grad(): # 推論時には勾配は不要
        for data, targets in loader_test:
 
            data = data.to(device) #  GPUを使用するため，to()で明示的に指定
            targets = targets.to(device) # 同上
 
            outputs = trained_model(data) # 順伝播の計算
 
            # 推論結果の取得と正誤判定
            _, predicted = torch.max(outputs.data, 1) # 確率が最大のラベルを取得
            correct += predicted.eq(targets.data.view_as(predicted)).sum() # 正解ならば正解数をカウントアップ

            loss = loss_fn(outputs, targets)
            running_loss += loss.item()
    
    # 正解率を計算
    data_num = len(loader_test.dataset) # テストデータの総数
    val_loss = running_loss / len(loader_test)
    print('\nTest Accuracy: {}/{} ({:.1f}%) loss: {:.4f}\n'.format(correct, data_num, 100. * correct / data_num, val_loss))
 
 
def main():
 
    # 1. GPUの設定（PyTorchでは明示的に指定する必要がある）
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(device)
 
    # 2. ハイパーパラメータの設定（最低限の設定）
    batch_size = 100
    num_classes = 10
    epochs = 20
 
    # 3. MNISTのデータセットを取得
    from sklearn.datasets import fetch_openml
    mnist = fetch_openml('mnist_784', version=1,)
 
    # 4. データの設定（入力データは閉区間[0, 1]に正規化する）
    x = mnist.data / 255
    y = mnist.target.astype(np.int32)
 
    # 5. DataLoaderの作成
    from torch.utils.data import TensorDataset, DataLoader
    from sklearn.model_selection import train_test_split
 
    # 5-1. データを学習用とテスト用に分割
    x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=1/7, random_state=0)
 
    # 5-2. データのフォーマットを変換：PyTorchでの形式 = [画像数，チャネル数，高さ，幅]
    x_train = x_train.values.reshape(60000, 28 * 28)
    x_test = x_test.values.reshape(10000, 28 *28)

    from sklearn.preprocessing import MinMaxScaler
    scaler = MinMaxScaler(feature_range=(-1, 1))

    scaler.fit(x)

    x_train = scaler.transform(x_train)
    x_test = scaler.transform(x_test)

    print(x_train.max(), x_train.min())
    print(x_test.max(), x_test.min())

    # 5-3. PyTorchのテンソルに変換
    x_train = torch.Tensor(x_train)
#    x_train.requires_grad_()
    x_test = torch.Tensor(x_test)
    y_train = torch.LongTensor(y_train.to_numpy(dtype=np.float64))
    y_test = torch.LongTensor(y_test.to_numpy(dtype=np.float64))
 
    # 5-4. 入力（x）とラベル（y）を組み合わせて最終的なデータを作成
    ds_train = TensorDataset(x_train, y_train)
    ds_test = TensorDataset(x_test, y_test)
 
    # 5-5. DataLoaderを作成
    loader_train = DataLoader(ds_train, batch_size=batch_size, shuffle=True)
    loader_test = DataLoader(ds_test, batch_size=batch_size, shuffle=False)
 
    # 6. モデル作成
#    model = net.CNN(num_classes=num_classes).to(device)
    vanilla_model = net.Net(1000,10).to(device)
    energy_model = net.Net(1000,10).to(device)
    #print(model) # ネットワークの詳細を確認用に表示
 
    # 7. 損失関数を定義
    loss_fn = nn.CrossEntropyLoss()
 
    # 8. 最適化手法を定義（ここでは例としてAdamを選択）
    from torch import optim
    vanilla_optimizer = optim.Adam(vanilla_model.parameters())
    energy_optimizer = optim.Adam(energy_model.parameters())

    # 9. 学習（エポック終了時点ごとにテスト用データで評価）
    print('Begin train')
    for epoch in range(1, epochs+1):
        print('Epoch [%d/%d]' % (epoch,epochs))
        print("--Vanilla Model--")
        train_vanilla(loader_train, vanilla_model, vanilla_optimizer, loss_fn, device, epochs, epoch)
        test_vanilla(loader_test, vanilla_model, loss_fn, device)
        print("--Energy Model--")
        train_energy(loader_train, energy_model, energy_optimizer, loss_fn, device, epochs, epoch)
        test_energy(loader_test, energy_model, loss_fn, device)
 
 
if __name__ == '__main__':
    main()
